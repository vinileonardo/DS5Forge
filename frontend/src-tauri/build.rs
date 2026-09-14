use std::{env, fs, path::PathBuf};

fn main() {
    let attributes = if cfg!(target_os = "windows") {
        let icon_path = ensure_placeholder_windows_icon();
        tauri_build::Attributes::new()
            .windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path(icon_path))
    } else {
        tauri_build::Attributes::new()
    };

    tauri_build::try_build(attributes).expect("failed to run tauri build helpers");
}

fn ensure_placeholder_windows_icon() -> PathBuf {
    let manifest_dir = PathBuf::from(
        env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by Cargo"),
    );
    let icon_dir = manifest_dir.join("icons");
    let icon_path = icon_dir.join("icon.ico");

    if !icon_path.exists() {
        fs::create_dir_all(&icon_dir).expect("failed to create Tauri icon directory");
        fs::write(&icon_path, placeholder_icon_bytes())
            .expect("failed to write P1 placeholder Windows icon");
    }

    icon_path
}

fn placeholder_icon_bytes() -> Vec<u8> {
    const WIDTH: u32 = 32;
    const HEIGHT: u32 = 32;
    const PIXEL_BYTES: u32 = WIDTH * HEIGHT * 4;
    const MASK_ROW_BYTES: u32 = ((WIDTH + 31) / 32) * 4;
    const MASK_BYTES: u32 = MASK_ROW_BYTES * HEIGHT;
    const DIB_BYTES: u32 = 40 + PIXEL_BYTES + MASK_BYTES;
    const IMAGE_OFFSET: u32 = 6 + 16;

    let mut data = Vec::with_capacity((IMAGE_OFFSET + DIB_BYTES) as usize);

    push_u16(&mut data, 0);
    push_u16(&mut data, 1);
    push_u16(&mut data, 1);

    data.push(WIDTH as u8);
    data.push(HEIGHT as u8);
    data.push(0);
    data.push(0);
    push_u16(&mut data, 1);
    push_u16(&mut data, 32);
    push_u32(&mut data, DIB_BYTES);
    push_u32(&mut data, IMAGE_OFFSET);

    push_u32(&mut data, 40);
    push_u32(&mut data, WIDTH);
    push_u32(&mut data, HEIGHT * 2);
    push_u16(&mut data, 1);
    push_u16(&mut data, 32);
    push_u32(&mut data, 0);
    push_u32(&mut data, PIXEL_BYTES);
    push_u32(&mut data, 0);
    push_u32(&mut data, 0);
    push_u32(&mut data, 0);
    push_u32(&mut data, 0);

    for y in (0..HEIGHT).rev() {
        for x in 0..WIDTH {
            let border = x < 2 || y < 2 || x >= WIDTH - 2 || y >= HEIGHT - 2;
            let glyph = (8..=11).contains(&x) && (7..=24).contains(&y)
                || (8..=20).contains(&x) && ((7..=10).contains(&y) || (21..=24).contains(&y))
                || (19..=22).contains(&x) && (10..=21).contains(&y);
            let (red, green, blue) = if border || glyph {
                (59_u8, 130_u8, 246_u8)
            } else {
                (11_u8, 16_u8, 32_u8)
            };
            data.extend_from_slice(&[blue, green, red, 255]);
        }
    }

    data.resize(data.len() + MASK_BYTES as usize, 0);
    data
}

fn push_u16(buffer: &mut Vec<u8>, value: u16) {
    buffer.extend_from_slice(&value.to_le_bytes());
}

fn push_u32(buffer: &mut Vec<u8>, value: u32) {
    buffer.extend_from_slice(&value.to_le_bytes());
}
