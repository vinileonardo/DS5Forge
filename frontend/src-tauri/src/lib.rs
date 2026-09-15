use serde::Serialize;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Debug, Clone, Serialize)]
pub struct LifecycleSnapshot {
    pub state: String,
    pub pid: Option<u32>,
    pub attempt: u32,
    pub message: Option<String>,
}

struct CoreSupervisor {
    child: Mutex<Option<CommandChild>>,
    snapshot: Mutex<LifecycleSnapshot>,
    stopping: Mutex<bool>,
    restart_count: Mutex<u32>,
    generation: Mutex<u64>,
}

impl Default for CoreSupervisor {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            snapshot: Mutex::new(LifecycleSnapshot {
                state: "desktop_starting".into(),
                pid: None,
                attempt: 0,
                message: None,
            }),
            stopping: Mutex::new(false),
            restart_count: Mutex::new(0),
            generation: Mutex::new(0),
        }
    }
}

fn set_snapshot(app: &AppHandle, state: &CoreSupervisor, value: &str, message: Option<String>) {
    if let Ok(mut snapshot) = state.snapshot.lock() {
        snapshot.state = value.to_owned();
        snapshot.message = message;
        snapshot.pid = state
            .child
            .lock()
            .ok()
            .and_then(|child| child.as_ref().map(CommandChild::pid));
    }
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_tooltip(Some(format!("DS5Forge · Core: {value}")));
    }
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn health_ready() -> bool {
    let address = ("127.0.0.1", 8765)
        .to_socket_addrs()
        .ok()
        .and_then(|mut addresses| addresses.next());
    let Some(address) = address else { return false };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(250)));
    if stream
        .write_all(b"GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut body = Vec::new();
    if stream.read_to_end(&mut body).is_err() {
        return false;
    }
    let text = String::from_utf8_lossy(&body);
    text.contains("200 OK") && text.contains("\"process_alive\":true")
}

fn request_core_shutdown() {
    let address = ("127.0.0.1", 8765)
        .to_socket_addrs()
        .ok()
        .and_then(|mut addresses| addresses.next());
    let Some(address) = address else { return };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.write_all(
        b"POST /api/v1/lifecycle/stop HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
    );
    let mut response = [0_u8; 256];
    let _ = stream.read(&mut response);
}

fn core_api_is_open() -> bool {
    let address = ("127.0.0.1", 8765)
        .to_socket_addrs()
        .ok()
        .and_then(|mut addresses| addresses.next());
    address
        .map(|value| TcpStream::connect_timeout(&value, Duration::from_millis(100)).is_ok())
        .unwrap_or(false)
}

fn wait_for_core_shutdown(attempts: u32) -> bool {
    for _ in 0..attempts {
        if !core_api_is_open() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

fn start_core_internal(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<CoreSupervisor>();
    if state
        .child
        .lock()
        .map_err(|_| "core state lock poisoned")?
        .is_some()
    {
        return Ok(());
    }
    *state
        .stopping
        .lock()
        .map_err(|_| "core state lock poisoned")? = false;
    let attempt = {
        let mut count = state
            .restart_count
            .lock()
            .map_err(|_| "core state lock poisoned")?;
        *count = count.saturating_add(1);
        *count
    };
    let generation = {
        let mut value = state
            .generation
            .lock()
            .map_err(|_| "core state lock poisoned")?;
        *value = (*value).saturating_add(1);
        *value
    };
    set_snapshot(app, &state, "core_starting", None);
    if let Ok(mut snapshot) = state.snapshot.lock() {
        snapshot.attempt = attempt;
    }
    let command = match app
        .shell()
        .sidecar("ds5forge-core")
        .map_err(|error| format!("sidecar command unavailable: {error}"))
    {
        Ok(command) => command,
        Err(error) => {
            set_snapshot(app, &state, "core_start_failed", Some(error.clone()));
            return Err(error);
        }
    };
    let (mut events, child) = match command
        .args(["--headless", "--host", "127.0.0.1", "--port", "8765"])
        .spawn()
    {
        Ok(value) => value,
        Err(error) => {
            let message = format!("sidecar could not start: {error}");
            set_snapshot(app, &state, "core_start_failed", Some(message.clone()));
            return Err(message);
        }
    };
    if let Ok(mut children) = state.child.lock() {
        *children = Some(child);
    }
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        for _ in 0..80 {
            if health_ready() {
                let current = app_handle.state::<CoreSupervisor>();
                let current_generation = current.generation.lock().map(|value| *value).unwrap_or(0);
                if current_generation == generation {
                    set_snapshot(&app_handle, &current, "core_ready", None);
                    set_snapshot(&app_handle, &current, "application_ready", None);
                }
                break;
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
        let current = app_handle.state::<CoreSupervisor>();
        let current_generation = current.generation.lock().map(|value| *value).unwrap_or(0);
        if current_generation == generation
            && current
                .snapshot
                .lock()
                .map(|snapshot| snapshot.state == "core_starting")
                .unwrap_or(false)
        {
            set_snapshot(
                &app_handle,
                &current,
                "core_timeout",
                Some("core health did not become ready".into()),
            );
            let _ = stop_core_internal(&app_handle);
            set_snapshot(
                &app_handle,
                &current,
                "core_timeout",
                Some("core health did not become ready".into()),
            );
        }
    });
    let monitor_app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            if let CommandEvent::Terminated(payload) = event {
                let state = monitor_app.state::<CoreSupervisor>();
                // A coordinated stop/start bumps the generation. A monitor for
                // a replaced child must not take or restart the new handle.
                let current_generation = state.generation.lock().map(|value| *value).unwrap_or(0);
                if current_generation != generation {
                    break;
                }
                // The process handle is no longer reusable after termination;
                // remove it before bounded recovery tries to spawn a fresh one.
                if let Ok(mut child) = state.child.lock() {
                    let _ = child.take();
                }
                let stopping = state.stopping.lock().map(|value| *value).unwrap_or(true);
                if stopping {
                    let timed_out = state
                        .snapshot
                        .lock()
                        .map(|snapshot| snapshot.state == "core_timeout")
                        .unwrap_or(false);
                    if !timed_out {
                        set_snapshot(&monitor_app, &state, "core_stopped", None);
                    }
                    break;
                }
                set_snapshot(
                    &monitor_app,
                    &state,
                    "core_crashed",
                    Some(format!("core exited: {:?}", payload.code)),
                );
                let can_restart = state
                    .restart_count
                    .lock()
                    .map(|value| *value < 4)
                    .unwrap_or(false);
                if can_restart {
                    tokio::time::sleep(Duration::from_secs(1)).await;
                    let stopping = state.stopping.lock().map(|value| *value).unwrap_or(true);
                    if stopping {
                        // A coordinated stop/quit happened during backoff; do
                        // not resurrect the sidecar.
                        break;
                    }
                    if let Err(error) = start_core_internal(&monitor_app) {
                        set_snapshot(&monitor_app, &state, "core_start_failed", Some(error));
                    }
                } else {
                    set_snapshot(
                        &monitor_app,
                        &state,
                        "core_start_failed",
                        Some("restart limit reached".into()),
                    );
                }
                break;
            }
        }
    });
    Ok(())
}

fn stop_core_internal(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<CoreSupervisor>();
    *state
        .stopping
        .lock()
        .map_err(|_| "core state lock poisoned")? = true;
    if let Ok(mut generation) = state.generation.lock() {
        *generation = (*generation).saturating_add(1);
    }
    set_snapshot(app, &state, "core_stopping", None);
    let child = state
        .child
        .lock()
        .map_err(|_| "core state lock poisoned")?
        .take();
    if let Some(child) = child {
        // Ask the sidecar to release hardware/tunnel and terminate itself. A
        // one-file PyInstaller bootloader only exits once its child exits, so
        // waiting for the loopback port to close avoids orphaning that child.
        let api_was_open = core_api_is_open();
        request_core_shutdown();
        let graceful = api_was_open && wait_for_core_shutdown(12);
        if !graceful {
            let kill_error = child.kill().err();
            if !wait_for_core_shutdown(32) {
                let message = match kill_error {
                    Some(error) => format!("core shutdown failed: {error}"),
                    None => "core API remained reachable after shutdown timeout".to_owned(),
                };
                set_snapshot(app, &state, "shutdown_timeout", Some(message.clone()));
                return Err(message);
            }
        }
    }
    set_snapshot(app, &state, "core_stopped", None);
    Ok(())
}

#[tauri::command]
fn lifecycle(state: State<'_, CoreSupervisor>) -> Result<LifecycleSnapshot, String> {
    state
        .snapshot
        .lock()
        .map(|snapshot| snapshot.clone())
        .map_err(|_| "core state lock poisoned".into())
}

#[tauri::command]
fn start_core(app: AppHandle) -> Result<LifecycleSnapshot, String> {
    start_core_internal(&app)?;
    lifecycle(app.state::<CoreSupervisor>())
}

#[tauri::command]
fn stop_core(app: AppHandle) -> Result<LifecycleSnapshot, String> {
    stop_core_internal(&app)?;
    lifecycle(app.state::<CoreSupervisor>())
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
    let status = MenuItem::with_id(app, "status", "Core status", false, None::<&str>)?;
    let show_hide = MenuItem::with_id(app, "show-hide", "Show / Hide", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &status, &show_hide, &quit])?;
    let mut builder = TrayIconBuilder::with_id("main")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_main(app),
            "show-hide" => {
                if let Some(window) = app.get_webview_window("main") {
                    if window.is_visible().unwrap_or(true) {
                        let _ = window.hide();
                    } else {
                        show_main(app);
                    }
                }
            }
            "quit" => {
                let _ = stop_core_internal(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }
    builder.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();
    #[cfg(desktop)]
    {
        // This must be registered first so a second process is closed before
        // it can spawn another core sidecar.
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main(app);
        }));
    }
    builder = builder.plugin(tauri_plugin_shell::init());
    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ));
        builder = builder.plugin(tauri_plugin_process::init());
        builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    }
    builder
        .manage(CoreSupervisor::default())
        .invoke_handler(tauri::generate_handler![lifecycle, start_core, stop_core])
        .setup(|app| {
            if let Err(error) = setup_tray(app) {
                eprintln!("DS5Forge tray unavailable: {error}");
            }
            if let Err(error) = start_core_internal(app.handle()) {
                set_snapshot(
                    app.handle(),
                    &app.state::<CoreSupervisor>(),
                    "core_start_failed",
                    Some(error),
                );
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building DS5Forge Tauri application")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit) {
                let _ = stop_core_internal(app);
            }
        });
}
