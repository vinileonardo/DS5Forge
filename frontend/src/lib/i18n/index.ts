import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const LOCALE_STORAGE_KEY = "ds5forge.locale";
export const SUPPORTED_LOCALES = ["en-US", "pt-BR"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const english = {
  "nav.overview": "Overview",
  "nav.haptics": "Haptics",
  "nav.touchpad": "Touchpad",
  "nav.controller": "Controller Lab",
  "nav.games": "Games",
  "nav.profiles": "Profiles",
  "nav.diagnostics": "Diagnostics",
  "nav.settings": "Settings",
  "shell.wiredCompanion": "Wired companion",
  "shell.usbLocalOnly": "USB / local only",
  "shell.protocolError": "Protocol error",
  "shell.profile": "Profile",
  "shell.origin": "Origin",
  "shell.mode": "Mode",
  "shell.modeExclusive": "Exclusive",
  "shell.modeRemap": "Remap",
  "shell.modeNative": "Native",
  "shell.coreUnavailable":
    "The local core is unavailable. DS5Forge will retry automatically; use Settings > Restart Core or Diagnostics if it stays offline.",
  "shell.coreUntrusted": "The core returned data the client could not trust. Check Diagnostics.",
  "shell.viewDiagnostics": "View diagnostics",
  "status.coreOnline": "Local core online",
  "status.coreOffline": "Local core offline",
  "status.coreReconnecting": "Reconnecting",
  "status.controllerStale": "Controller state stale",
  "status.usb": "USB",
  "settings.eyebrow": "Client and core preferences",
  "settings.title": "Settings",
  "settings.description":
    "Keep the existing schema-v1 preferences visible without introducing a second local configuration system.",
  "settings.coreUnavailableTitle": "Core unavailable",
  "settings.coreUnavailableBody":
    "Core-backed preferences are unavailable, but desktop recovery controls and signed updates remain available.",
  "settings.coreSettingsUnavailable": "Core settings are unavailable.",
  "settings.savedTitle": "Saved",
  "settings.appearance": "Appearance",
  "settings.appearanceHelp":
    "The persisted theme remains authoritative. Dark is the default only when no saved value exists.",
  "settings.theme": "Theme",
  "settings.themeHelp": "Liquid Glass remains available when it is present in the core contract.",
  "settings.themeDark": "Dark",
  "settings.themeLight": "Light",
  "settings.themeLiquidGlass": "Liquid Glass",
  "settings.corePreferences": "Core preferences",
  "settings.corePreferencesHelp": "Theme and controller-button preferences are persisted by the local core.",
  "settings.waitingCorePreferences": "Waiting for persisted settings from the local core…",
  "settings.corePreferencesUnavailable": "Core preferences unavailable",
  "settings.corePreferencesUnavailableBody":
    "Desktop recovery, startup and signed update controls remain available below.",
  "settings.desktop": "Desktop",
  "settings.desktopHelp":
    "The Tauri shell owns the Python sidecar, tray, single-instance behavior and coordinated teardown.",
  "settings.applicationVersion": "Application version",
  "settings.shellPlatform": "Shell platform",
  "settings.browserUnknown": "Browser / unknown",
  "settings.lifecycle": "Lifecycle",
  "settings.restartHelp": "Restart releases controller outputs before starting the core again.",
  "settings.startup": "Startup",
  "settings.startupHelp": "Autostart is disabled by default and can be reversed at any time.",
  "settings.autostartIntegration": "Uses the official Tauri autostart integration.",
  "settings.autostartShellOnly":
    "Available in the installed desktop shell; browser preview cannot modify Windows startup.",
  "settings.autostartEnabled": "Autostart enabled.",
  "settings.autostartDisabled": "Autostart disabled.",
  "settings.updates": "Updates",
  "settings.updatesHelp":
    "Only HTTPS metadata with a detached Tauri signature is accepted. Failed updates leave the current install intact.",
  "settings.updateProgressHelp": "Windows installer updates use passive progress feedback.",
  "settings.updater": "Updater",
  "settings.restartToApply": "Restart to apply",
  "settings.advancedRemote": "Advanced · Remote Access",
  "settings.remoteAccess": "Remote Access",
  "settings.remoteAccessHelp":
    "OFF by default. Pairing starts locally, stores only session hashes, and authenticates remote HTTP/WebSocket with a Secure HttpOnly cookie.",
  "settings.registeredOrigin": "Registered HTTPS origin",
  "settings.registeredOriginHelp":
    "Use the exact HTTPS origin served by the remote access gateway; no path, query or wildcard.",
  "settings.status": "Status",
  "settings.sessions": "session(s)",
  "settings.startPairing": "Start one-time pairing",
  "settings.disableRemote": "Disable remote",
  "settings.pairingCode": "One-time pairing code",
  "settings.expires": "expires",
  "settings.active": "active",
  "settings.inactive": "inactive",
  "settings.revoke": "Revoke",
  "settings.tunnelDefaultMessage": "Explicit configuration only; no download or silent install.",
  "settings.tunnelExecutable": "Cloudflared executable",
  "settings.tunnelExecutableHelp":
    "Optional absolute executable path or a user-managed PATH entry. DS5Forge never downloads it.",
  "settings.tunnelYaml": "Cloudflared YAML config",
  "settings.tunnelYamlHelp":
    "Absolute YAML path; raw tunnel tokens are rejected and the file is never exported.",
  "settings.validateTunnel": "Validate tunnel config",
  "settings.startTunnel": "Start tunnel",
  "settings.stopTunnel": "Stop tunnel",
  "settings.remoteDisabled": "Remote access disabled; sessions and tunnel state were closed.",
  "settings.tunnelValidated":
    "Cloudflared configuration validated. It remains stopped until explicitly started.",
  "settings.advanced": "Advanced",
  "settings.advancedHelp": "Diagnostics exports are bounded and sanitized for support review.",
  "settings.apiEndpoint": "API endpoint",
  "settings.transport": "Transport",
  "settings.usbWiredOnly": "USB / wired only",
  "settings.virtualController": "Virtual controller",
  "settings.virtualUnavailable": "Unavailable by decision; no driver is installed",
  "settings.exportSupport": "Export Support Bundle",
  "settings.localService": "Local service",
  "settings.localServiceHelp": "Informational only. P1 does not expose an arbitrary endpoint editor.",
  "settings.transportScope": "Transport scope",
  "settings.coreStart": "Core start",
  "settings.coreStartManaged": "Installed desktop shell manages the packaged core automatically.",
  "settings.micButton": "Microphone button behavior",
  "settings.micButtonHelp":
    "These labels map directly to the current master, rumble and trackpad wire values.",
  "settings.buttonAction": "Button action",
  "settings.micMasterLabel": "Master behavior",
  "settings.micMasterHelp": "Toggle the master behavior defined by the core.",
  "settings.micRumbleLabel": "Haptics",
  "settings.micRumbleHelp": "Toggle audio-driven rumble from the controller button.",
  "settings.micTrackpadLabel": "Touchpad",
  "settings.micTrackpadHelp": "Toggle touchpad mouse behavior from the controller button.",
  "settings.language": "Language",
  "settings.languageHelp": "The language preference is stored locally and works offline.",
  "settings.english": "English (US)",
  "settings.portuguese": "Português (Brasil)",
  "settings.saveSettings": "Save settings",
  "settings.saving": "Saving…",
  "settings.saved": "Settings saved.",
  "settings.unsaved": "Unsaved settings",
  "settings.upToDate": "Settings are up to date.",
  "settings.restartCore": "Restart core",
  "settings.restarting": "Restarting…",
  "settings.restartingAria": "Restarting local core",
  "settings.restartingStatus": "Restarting local core…",
  "settings.restartOverlayBody":
    "DS5Forge is releasing the current controller session and waiting for the new core to become ready.",
  "settings.stoppingCore": "Stopping local core safely…",
  "settings.startingCore": "Starting local core…",
  "settings.waitingControllerServices": "Waiting for controller services…",
  "settings.coreReadyTimeout": "Core did not become ready within 30 seconds.",
  "settings.restartFailedState": "Core restart failed in state",
  "settings.coreRestarted": "Core restarted. Hardware outputs were released before the new core started.",
  "settings.checkForUpdates": "Check for updates",
  "settings.checking": "Checking…",
  "settings.checkingSignedUpdates": "Checking for signed updates…",
  "settings.noSignedUpdate": "No signed update is available.",
  "settings.downloadingUpdate": "Downloading signed update…",
  "settings.installingUpdate": "Installing update…",
  "settings.updateInstalledRelaunching": "Update installed; relaunching DS5Forge automatically…",
  "settings.updateInstalledShell": "Update installed. Relaunch the desktop shell to apply it.",
  "settings.updateUnavailable": "Update check unavailable in this shell.",
  "settings.supportExported": "Support Bundle exported with secrets and sensitive paths redacted.",
  "settings.off": "off",
  "settings.launchAtSignIn": "Launch at Windows sign-in",
  "games.eyebrow": "Compatibility control",
  "games.title": "Games",
  "games.loadingDescription": "Loading the local game registry…",
  "games.description":
    "Apply profiles by foreground executable while keeping Native DualSense input as the safe default.",
  "games.refreshRegistry": "Refresh registry",
  "games.dataUnavailable": "Games data unavailable",
  "games.reconnectingCore": "Reconnecting local core",
  "games.coreOffline": "Local core offline",
  "games.coreStaleBody":
    "The registry may still be visible, but foreground, active-game and automation state are stale until the WebSocket reconnects.",
  "games.runningCandidates": "Running and recent candidates",
  "games.candidatesHelp": "Running and recent executables are suggestions only; saving remains explicit.",
  "games.pickExecutable": "Pick .exe",
  "games.useCandidate": "Use candidate",
  "games.noCandidates": "No running or recent executable candidates were found.",
  "games.nativeDescription": "Native keeps DualSense input visible to the game.",
  "games.remapDescription": "Remapping creates keyboard/mouse output and may duplicate input.",
  "games.exclusiveDescription":
    "Exclusive requires a verified virtual output and physical suppression provider.",
  "games.adaptiveTriggerMode": "Adaptive triggers for this game",
  "games.adaptiveTriggerModeHelp":
    "Native leaves game behavior untouched. Reactive is an explicit opt-in to a DS5Forge-generated effect that reacts to audio and trigger input. Off neutralizes DS5Forge trigger output.",
  "games.adaptiveNative": "Native (no generated effect)",
  "games.adaptiveReactive": "Reactive (DS5Forge-generated)",
  "games.adaptiveOff": "Off (neutralize DS5Forge output)",
  "games.exclusiveToggle": "Exclusive input mode",
  "games.exclusiveActive": "Physical input suppression is active only while the verified session is alive.",
  "games.exclusiveUnavailable":
    "Unavailable until the provider is installed, verified and validated on Windows.",
  "games.provider": "Provider",
  "games.outputReports": "Output reports",
  "games.suppressionVerified": "Suppression verified",
  "games.doubleInputRisk": "Double-input risk",
  "games.foregroundTitle": "Foreground",
  "games.foregroundHelp": "Identity uses the executable, never the mutable window title.",
  "games.executable": "Executable",
  "games.desktopUnavailable": "Desktop / unavailable",
  "games.executablePath": "Executable path",
  "games.windowTitle": "Window title",
  "games.observation": "Observation",
  "games.statusRealtime": "realtime",
  "games.statusStale": "stale",
  "games.statusReconnecting": "reconnecting",
  "games.activeGameTitle": "Active game",
  "games.activeGameHelp": "Updates from realtime state without a page reload.",
  "games.profile": "Profile",
  "games.origin": "Origin",
  "games.rule": "Rule",
  "games.manualOverride": "Manual override",
  "games.overrideActive": "active",
  "games.overrideNone": "none",
  "games.noActiveGame": "No active game",
  "games.noActiveGameHelp": "Foreground is not currently matched by an enabled rule.",
  "games.automation": "Game automation",
  "games.automationOn": "Rules are evaluated on real foreground transitions",
  "games.automationOff": "Automation is off",
  "games.compatibilityTitle": "Compatibility mode",
  "games.compatibilityHelp": "Mode changes release all synthetic outputs before applying.",
  "games.inputMode": "Input mode",
  "games.inputModeHelp": "Native never creates synthetic output. Remap does not require XInput.",
  "games.nativeDualSense": "Native DualSense",
  "games.remapKeyboardMouse": "Remap keyboard/mouse",
  "games.virtualXInput": "Virtual / XInput",
  "games.virtualProviderAvailable": "Virtual provider available",
  "games.virtualProviderAvailableBody":
    "Physical suppression is reported by the injected provider and remains explicit.",
  "games.virtualUnavailable": "Virtual / XInput unavailable",
  "games.virtualUnavailableBody":
    "No approved provider with reliable physical suppression is installed. The requested mode will be rejected and the current state will remain unchanged.",
  "games.possibleDoubleInput": "Possible double input in Remap",
  "games.possibleDoubleInputBody":
    "Remap adds synthetic keyboard/mouse output while the physical controller remains visible.",
  "games.physicalVisible": "Physical input visible",
  "games.virtualActive": "Virtual input active",
  "games.exitPolicyTitle": "Exit policy",
  "games.exitPolicyHelp": "What happens when the foreground game closes or changes to desktop.",
  "games.onExit": "On game exit",
  "games.restorePrevious": "Restore previous profile",
  "games.applyDefault": "Apply Default profile",
  "games.keepCurrent": "Keep current state",
  "games.manualOverrideHelp":
    "Manual profile or mode changes mark the active context as a manual override until a real foreground transition.",
  "games.registryTitle": "Game registry",
  "games.registryHelp":
    "Match one or more executable names, with an optional exact path for single-executable rules.",
  "games.enabled": "Enabled",
  "games.disabled": "Disabled",
  "games.edit": "Edit",
  "games.testMatch": "Test match",
  "games.remove": "Remove",
  "games.removeRuleConfirm": "Remove game rule",
  "games.noGames": "No games registered. Add an executable rule below.",
  "games.matchExplanation": "Match explanation",
  "games.ruleEvaluations": "Rule evaluations",
  "games.matched": "Matched",
  "games.notMatched": "Not matched",
  "games.ruleId": "Rule ID",
  "games.displayName": "Display name",
  "games.executables": "Executables",
  "games.executablesHelp": "Comma-separated process names, for example game.exe, launcher.exe.",
  "games.optionalPath": "Optional full path",
  "games.optionalPathHelp": "Only available when the rule has exactly one executable name.",
  "games.profileHelp": "Choose a persisted profile; names are not free-form output commands.",
  "games.automationMode": "Automation mode",
  "games.ruleEnabled": "Rule enabled",
  "games.ruleEnabledHelp": "Evaluate these executable identities during foreground transitions.",
  "games.saveGameRule": "Save game rule",
  "games.saving": "Saving…",
  "games.clear": "Clear",
  "games.advancedMappings": "Advanced · Mappings and chords",
  "games.mappings": "Mappings",
  "games.mappingsHelp": "Controller button to validated keyboard or mouse output.",
  "games.mappingId": "Mapping ID",
  "games.controllerInput": "Controller input",
  "games.outputKind": "Output kind",
  "games.keyboard": "Keyboard",
  "games.mouse": "Mouse",
  "games.outputCode": "Output code",
  "games.keyboardCodeHelp": "Use one key or a + combination, for example SPACE or CTRL+SHIFT+S.",
  "games.mouseCodeHelp": "Use left, right, middle, mouse4 or mouse5.",
  "games.allGames": "all games",
  "games.gameScope": "Game scope (optional)",
  "games.mappingScopeHelp": "Leave blank to apply this mapping in every remap context.",
  "games.chordScopeHelp": "Leave blank to apply this chord in every remap context.",
  "games.debounce": "Debounce (ms)",
  "games.mappingEnabled": "Mapping enabled",
  "games.mappingEnabledHelp": "Allow this mapping to produce output in its configured scope.",
  "games.saveMapping": "Save mapping",
  "games.chords": "Chords",
  "games.chordsHelp": "Two or more inputs; chords take precedence during the bounded activation window.",
  "games.chordId": "Chord ID",
  "games.inputsComma": "Inputs (comma-separated)",
  "games.chordWindow": "Chord window (ms)",
  "games.chordEnabled": "Chord enabled",
  "games.chordEnabledHelp": "Allow this chord to win over simple mappings during its bounded window.",
  "games.saveChord": "Save chord",
  "games.conflictDiagnostics": "Conflict diagnostics",
  "games.conflictDiagnosticsHelp":
    "Process-name evidence only; DS5Forge never kills or reconfigures other software.",
  "games.possibleInputConflict": "Possible input conflict",
  "games.possibleInputConflictBody":
    "A remapper or Steam process is running. Its active input configuration was not inferred.",
  "games.notDetected": "not detected",
  "games.runtimeLoading": "Runtime loading",
  "games.pending": "pending",
  "controller.lightbarIntensity": "RGB intensity",
  "controller.lightbarIntensityHelp":
    "Scales the RGB lightbar output. RGB intensity is separate from the Player LEDs.",
  "controller.playerLeds": "Player LEDs",
  "controller.playerLedsHelp":
    "Player LED output is a separate control from the RGB lightbar and keeps its own state.",
  "controller.playerLedsEnabled": "Player LEDs enabled",
  "controller.playerLedsIntensity": "Player LED intensity",
  "controller.calibrationHint":
    "Calibration affects DS5Forge Exclusive virtual mirroring and visualization metadata. Native physical input is never changed.",
  "exclusive.title": "Exclusive input",
  "exclusive.unavailable": "Unavailable until provider provenance and Windows validation are proven.",
} as const;

export type TranslationKey = keyof typeof english;
type Dictionary = Record<TranslationKey, string>;

const portuguese: Dictionary = {
  "nav.overview": "Visão geral",
  "nav.haptics": "Hápticos",
  "nav.touchpad": "Touchpad",
  "nav.controller": "Laboratório do controle",
  "nav.games": "Jogos",
  "nav.profiles": "Perfis",
  "nav.diagnostics": "Diagnóstico",
  "nav.settings": "Configurações",
  "shell.wiredCompanion": "Companheiro com fio",
  "shell.usbLocalOnly": "Somente USB / local",
  "shell.protocolError": "Erro de protocolo",
  "shell.profile": "Perfil",
  "shell.origin": "Origem",
  "shell.mode": "Modo",
  "shell.modeExclusive": "Modo exclusivo",
  "shell.modeRemap": "Remapeamento",
  "shell.modeNative": "Nativo",
  "shell.coreUnavailable":
    "O núcleo local está indisponível. O DS5Forge tentará reconectar automaticamente; use Configurações > Reiniciar núcleo ou o Diagnóstico se continuar offline.",
  "shell.coreUntrusted":
    "O núcleo retornou dados nos quais o cliente não pôde confiar. Verifique o Diagnóstico.",
  "shell.viewDiagnostics": "Ver diagnóstico",
  "status.coreOnline": "Núcleo local online",
  "status.coreOffline": "Núcleo local offline",
  "status.coreReconnecting": "Reconectando",
  "status.controllerStale": "Estado do controle desatualizado",
  "status.usb": "USB",
  "settings.eyebrow": "Preferências do cliente e do núcleo",
  "settings.title": "Configurações",
  "settings.description":
    "Mantém as preferências schema-v1 visíveis sem introduzir um segundo sistema de configuração local.",
  "settings.coreUnavailableTitle": "Núcleo indisponível",
  "settings.coreUnavailableBody":
    "As preferências do núcleo estão indisponíveis, mas os controles de recuperação e as atualizações assinadas continuam disponíveis.",
  "settings.coreSettingsUnavailable": "As configurações do núcleo estão indisponíveis.",
  "settings.savedTitle": "Salvo",
  "settings.appearance": "Aparência",
  "settings.appearanceHelp":
    "O tema salvo continua sendo a referência. Escuro é o padrão somente quando não há valor salvo.",
  "settings.theme": "Tema",
  "settings.themeHelp": "Liquid Glass continua disponível quando estiver presente no contrato do núcleo.",
  "settings.themeDark": "Escuro",
  "settings.themeLight": "Claro",
  "settings.themeLiquidGlass": "Liquid Glass",
  "settings.corePreferences": "Preferências do núcleo",
  "settings.corePreferencesHelp":
    "O tema e as preferências dos botões do controle são salvos pelo núcleo local.",
  "settings.waitingCorePreferences": "Aguardando as configurações salvas do núcleo local…",
  "settings.corePreferencesUnavailable": "Preferências do núcleo indisponíveis",
  "settings.corePreferencesUnavailableBody":
    "Os controles de recuperação, inicialização e atualização assinada continuam disponíveis abaixo.",
  "settings.desktop": "Área de trabalho",
  "settings.desktopHelp":
    "O shell Tauri gerencia o sidecar Python, a bandeja, a instância única e o encerramento coordenado.",
  "settings.applicationVersion": "Versão do aplicativo",
  "settings.shellPlatform": "Plataforma do shell",
  "settings.browserUnknown": "Navegador / desconhecido",
  "settings.lifecycle": "Ciclo de vida",
  "settings.restartHelp": "Reiniciar libera as saídas do controle antes de iniciar o núcleo novamente.",
  "settings.startup": "Inicialização",
  "settings.startupHelp":
    "A inicialização automática vem desativada e pode ser revertida a qualquer momento.",
  "settings.autostartIntegration": "Usa a integração oficial de inicialização automática do Tauri.",
  "settings.autostartShellOnly":
    "Disponível no aplicativo desktop instalado; a prévia no navegador não pode alterar a inicialização do Windows.",
  "settings.autostartEnabled": "Inicialização automática ativada.",
  "settings.autostartDisabled": "Inicialização automática desativada.",
  "settings.updates": "Atualizações",
  "settings.updatesHelp":
    "Somente metadados HTTPS com assinatura Tauri separada são aceitos. Falhas de atualização mantêm a instalação atual intacta.",
  "settings.updateProgressHelp":
    "As atualizações do instalador do Windows mostram o progresso sem interromper o uso.",
  "settings.updater": "Atualizador",
  "settings.restartToApply": "Reiniciar para aplicar",
  "settings.advancedRemote": "Avançado · Acesso remoto",
  "settings.remoteAccess": "Acesso remoto",
  "settings.remoteAccessHelp":
    "Desativado por padrão. O pareamento começa localmente, armazena somente hashes de sessão e autentica HTTP/WebSocket remoto com cookie Secure HttpOnly.",
  "settings.registeredOrigin": "Origem HTTPS registrada",
  "settings.registeredOriginHelp":
    "Use a origem HTTPS exata fornecida pelo gateway de acesso remoto; sem caminho, query ou curinga.",
  "settings.status": "Status",
  "settings.sessions": "sessão(ões)",
  "settings.startPairing": "Iniciar pareamento único",
  "settings.disableRemote": "Desativar acesso remoto",
  "settings.pairingCode": "Código de pareamento único",
  "settings.expires": "expira às",
  "settings.active": "ativa",
  "settings.inactive": "inativa",
  "settings.revoke": "Revogar",
  "settings.tunnelDefaultMessage": "Somente configuração explícita; sem download ou instalação silenciosa.",
  "settings.tunnelExecutable": "Executável do Cloudflared",
  "settings.tunnelExecutableHelp":
    "Caminho absoluto opcional ou entrada do PATH gerenciada pelo usuário. O DS5Forge nunca faz o download.",
  "settings.tunnelYaml": "Configuração YAML do Cloudflared",
  "settings.tunnelYamlHelp":
    "Caminho YAML absoluto; tokens brutos de túnel são rejeitados e o arquivo nunca é exportado.",
  "settings.validateTunnel": "Validar configuração do túnel",
  "settings.startTunnel": "Iniciar túnel",
  "settings.stopTunnel": "Parar túnel",
  "settings.remoteDisabled": "Acesso remoto desativado; as sessões e o túnel foram encerrados.",
  "settings.tunnelValidated":
    "Configuração do Cloudflared validada. Ele continua parado até ser iniciado explicitamente.",
  "settings.advanced": "Avançado",
  "settings.advancedHelp": "As exportações de diagnóstico são limitadas e sanitizadas para suporte.",
  "settings.apiEndpoint": "Endpoint da API",
  "settings.transport": "Transporte",
  "settings.usbWiredOnly": "Somente USB / com fio",
  "settings.virtualController": "Controle virtual",
  "settings.virtualUnavailable": "Indisponível por decisão do projeto; nenhum driver é instalado",
  "settings.exportSupport": "Exportar pacote de suporte",
  "settings.localService": "Serviço local",
  "settings.localServiceHelp": "Somente informativo. O P1 não expõe um editor arbitrário de endpoint.",
  "settings.transportScope": "Escopo de transporte",
  "settings.coreStart": "Inicialização do núcleo",
  "settings.coreStartManaged": "O aplicativo desktop instalado gerencia automaticamente o núcleo empacotado.",
  "settings.micButton": "Comportamento do botão de microfone",
  "settings.micButtonHelp":
    "Estes rótulos correspondem diretamente aos valores de protocolo master, rumble e trackpad.",
  "settings.buttonAction": "Ação do botão",
  "settings.micMasterLabel": "Comportamento principal",
  "settings.micMasterHelp": "Alterna o comportamento principal definido pelo núcleo.",
  "settings.micRumbleLabel": "Hápticos",
  "settings.micRumbleHelp": "Alterna a vibração guiada por áudio pelo botão do controle.",
  "settings.micTrackpadLabel": "Touchpad",
  "settings.micTrackpadHelp": "Alterna o comportamento de mouse do touchpad pelo botão do controle.",
  "settings.language": "Idioma",
  "settings.languageHelp": "A preferência de idioma é salva localmente e funciona offline.",
  "settings.english": "English (EUA)",
  "settings.portuguese": "Português (Brasil)",
  "settings.saveSettings": "Salvar configurações",
  "settings.saving": "Salvando…",
  "settings.saved": "Configurações salvas.",
  "settings.unsaved": "Configurações não salvas",
  "settings.upToDate": "As configurações estão atualizadas.",
  "settings.restartCore": "Reiniciar núcleo",
  "settings.restarting": "Reiniciando…",
  "settings.restartingAria": "Reiniciando o núcleo local",
  "settings.restartingStatus": "Reiniciando o núcleo local…",
  "settings.restartOverlayBody":
    "O DS5Forge está liberando a sessão atual do controle e aguardando o novo núcleo ficar pronto.",
  "settings.stoppingCore": "Parando o núcleo local com segurança…",
  "settings.startingCore": "Iniciando o núcleo local…",
  "settings.waitingControllerServices": "Aguardando os serviços do controle…",
  "settings.coreReadyTimeout": "O núcleo não ficou pronto em até 30 segundos.",
  "settings.restartFailedState": "Falha ao reiniciar o núcleo no estado",
  "settings.coreRestarted":
    "Núcleo reiniciado. As saídas de hardware foram liberadas antes da nova inicialização.",
  "settings.checkForUpdates": "Verificar atualizações",
  "settings.checking": "Verificando…",
  "settings.checkingSignedUpdates": "Verificando atualizações assinadas…",
  "settings.noSignedUpdate": "Nenhuma atualização assinada está disponível.",
  "settings.downloadingUpdate": "Baixando atualização assinada…",
  "settings.installingUpdate": "Instalando atualização…",
  "settings.updateInstalledRelaunching": "Atualização instalada; reiniciando o DS5Forge automaticamente…",
  "settings.updateInstalledShell": "Atualização instalada. Reinicie o aplicativo desktop para aplicá-la.",
  "settings.updateUnavailable": "A verificação de atualização não está disponível neste ambiente.",
  "settings.supportExported": "Pacote de suporte exportado com segredos e caminhos sensíveis removidos.",
  "settings.off": "desativado",
  "settings.launchAtSignIn": "Iniciar ao entrar no Windows",
  "games.eyebrow": "Controle de compatibilidade",
  "games.title": "Jogos",
  "games.loadingDescription": "Carregando o registro local de jogos…",
  "games.description":
    "Aplique perfis pelo executável em primeiro plano mantendo a entrada DualSense nativa como padrão seguro.",
  "games.refreshRegistry": "Atualizar registro",
  "games.dataUnavailable": "Dados de jogos indisponíveis",
  "games.reconnectingCore": "Reconectando ao núcleo local",
  "games.coreOffline": "Núcleo local offline",
  "games.coreStaleBody":
    "O registro ainda pode aparecer, mas o primeiro plano, o jogo ativo e a automação ficam desatualizados até o WebSocket reconectar.",
  "games.runningCandidates": "Candidatos em execução e recentes",
  "games.candidatesHelp":
    "Executáveis em execução e recentes são apenas sugestões; salvar continua sendo uma ação explícita.",
  "games.pickExecutable": "Escolher .exe",
  "games.useCandidate": "Usar candidato",
  "games.noCandidates": "Nenhum executável em execução ou recente foi encontrado.",
  "games.nativeDescription": "Nativo mantém a entrada DualSense visível para o jogo.",
  "games.remapDescription": "O remapeamento cria saída de teclado/mouse e pode duplicar entradas.",
  "games.exclusiveDescription":
    "O modo exclusivo exige um provedor verificado de saída virtual e de supressão física.",
  "games.adaptiveTriggerMode": "Gatilhos adaptativos neste jogo",
  "games.adaptiveTriggerModeHelp":
    "Nativo não altera o comportamento do jogo. Reativo é uma opção explícita para um efeito gerado pelo DS5Forge que reage ao áudio e ao acionamento dos gatilhos. Desativado neutraliza a saída de gatilhos do DS5Forge.",
  "games.adaptiveNative": "Nativo (sem efeito gerado)",
  "games.adaptiveReactive": "Reativo (gerado pelo DS5Forge)",
  "games.adaptiveOff": "Desativado (neutraliza a saída do DS5Forge)",
  "games.exclusiveToggle": "Modo de entrada exclusivo",
  "games.exclusiveActive":
    "A supressão da entrada física fica ativa apenas enquanto a sessão verificada estiver viva.",
  "games.exclusiveUnavailable":
    "Indisponível até o provedor estar instalado, verificado e validado no Windows.",
  "games.provider": "Provedor",
  "games.outputReports": "Relatórios de saída",
  "games.suppressionVerified": "Supressão verificada",
  "games.doubleInputRisk": "Risco de entrada duplicada",
  "games.foregroundTitle": "Primeiro plano",
  "games.foregroundHelp": "A identidade usa o executável, nunca o título mutável da janela.",
  "games.executable": "Executável",
  "games.desktopUnavailable": "Área de trabalho / indisponível",
  "games.executablePath": "Caminho do executável",
  "games.windowTitle": "Título da janela",
  "games.observation": "Observação",
  "games.statusRealtime": "tempo real",
  "games.statusStale": "desatualizado",
  "games.statusReconnecting": "reconectando",
  "games.activeGameTitle": "Jogo ativo",
  "games.activeGameHelp": "Atualiza em tempo real sem recarregar a página.",
  "games.profile": "Perfil",
  "games.origin": "Origem",
  "games.rule": "Regra",
  "games.manualOverride": "Substituição manual",
  "games.overrideActive": "ativa",
  "games.overrideNone": "nenhuma",
  "games.noActiveGame": "Nenhum jogo ativo",
  "games.noActiveGameHelp": "O primeiro plano atual não corresponde a nenhuma regra ativada.",
  "games.automation": "Automação de jogos",
  "games.automationOn": "As regras são avaliadas em transições reais do primeiro plano",
  "games.automationOff": "A automação está desativada",
  "games.compatibilityTitle": "Modo de compatibilidade",
  "games.compatibilityHelp":
    "A troca de modo libera todas as saídas sintéticas antes de aplicar a alteração.",
  "games.inputMode": "Modo de entrada",
  "games.inputModeHelp": "Nativo nunca cria saída sintética. O remapeamento não exige XInput.",
  "games.nativeDualSense": "DualSense nativo",
  "games.remapKeyboardMouse": "Remapear teclado/mouse",
  "games.virtualXInput": "Virtual / XInput",
  "games.virtualProviderAvailable": "Provedor virtual disponível",
  "games.virtualProviderAvailableBody":
    "A supressão física é informada pelo provedor injetado e permanece explícita.",
  "games.virtualUnavailable": "Virtual / XInput indisponível",
  "games.virtualUnavailableBody":
    "Nenhum provedor aprovado com supressão física confiável está instalado. O modo solicitado será rejeitado e o estado atual será mantido.",
  "games.possibleDoubleInput": "Possível entrada duplicada no remapeamento",
  "games.possibleDoubleInputBody":
    "O remapeamento adiciona saída sintética de teclado/mouse enquanto o controle físico continua visível.",
  "games.physicalVisible": "Entrada física visível",
  "games.virtualActive": "Entrada virtual ativa",
  "games.exitPolicyTitle": "Política de saída",
  "games.exitPolicyHelp":
    "Define o que acontece quando o jogo em primeiro plano fecha ou volta para a área de trabalho.",
  "games.onExit": "Ao sair do jogo",
  "games.restorePrevious": "Restaurar perfil anterior",
  "games.applyDefault": "Aplicar perfil Default",
  "games.keepCurrent": "Manter estado atual",
  "games.manualOverrideHelp":
    "Alterações manuais de perfil ou modo marcam o contexto ativo como substituído até uma transição real do primeiro plano.",
  "games.registryTitle": "Registro de jogos",
  "games.registryHelp":
    "Associe um ou mais nomes de executável, com caminho exato opcional para regras de executável único.",
  "games.enabled": "Ativada",
  "games.disabled": "Desativada",
  "games.edit": "Editar",
  "games.testMatch": "Testar correspondência",
  "games.remove": "Remover",
  "games.removeRuleConfirm": "Remover regra do jogo",
  "games.noGames": "Nenhum jogo registrado. Adicione uma regra de executável abaixo.",
  "games.matchExplanation": "Explicação da correspondência",
  "games.ruleEvaluations": "Avaliações das regras",
  "games.matched": "Correspondeu",
  "games.notMatched": "Não correspondeu",
  "games.ruleId": "ID da regra",
  "games.displayName": "Nome de exibição",
  "games.executables": "Executáveis",
  "games.executablesHelp": "Nomes de processos separados por vírgula, por exemplo game.exe, launcher.exe.",
  "games.optionalPath": "Caminho completo opcional",
  "games.optionalPathHelp": "Disponível somente quando a regra possui exatamente um nome de executável.",
  "games.profileHelp": "Escolha um perfil salvo; nomes não são comandos livres de saída.",
  "games.automationMode": "Modo de automação",
  "games.ruleEnabled": "Regra ativada",
  "games.ruleEnabledHelp": "Avalia essas identidades de executável durante transições do primeiro plano.",
  "games.saveGameRule": "Salvar regra do jogo",
  "games.saving": "Salvando…",
  "games.clear": "Limpar",
  "games.advancedMappings": "Avançado · Mapeamentos e acordes",
  "games.mappings": "Mapeamentos",
  "games.mappingsHelp": "Botão do controle para saída validada de teclado ou mouse.",
  "games.mappingId": "ID do mapeamento",
  "games.controllerInput": "Entrada do controle",
  "games.outputKind": "Tipo de saída",
  "games.keyboard": "Teclado",
  "games.mouse": "Mouse",
  "games.outputCode": "Código de saída",
  "games.keyboardCodeHelp": "Use uma tecla ou combinação com +, por exemplo SPACE ou CTRL+SHIFT+S.",
  "games.mouseCodeHelp": "Use left, right, middle, mouse4 ou mouse5.",
  "games.allGames": "todos os jogos",
  "games.gameScope": "Escopo do jogo (opcional)",
  "games.mappingScopeHelp": "Deixe em branco para aplicar este mapeamento em todo contexto de remapeamento.",
  "games.chordScopeHelp": "Deixe em branco para aplicar este acorde em todo contexto de remapeamento.",
  "games.debounce": "Debounce (ms)",
  "games.mappingEnabled": "Mapeamento ativado",
  "games.mappingEnabledHelp": "Permite que este mapeamento produza saída no escopo configurado.",
  "games.saveMapping": "Salvar mapeamento",
  "games.chords": "Acordes",
  "games.chordsHelp": "Duas ou mais entradas; acordes têm precedência durante a janela limitada de ativação.",
  "games.chordId": "ID do acorde",
  "games.inputsComma": "Entradas (separadas por vírgula)",
  "games.chordWindow": "Janela do acorde (ms)",
  "games.chordEnabled": "Acorde ativado",
  "games.chordEnabledHelp":
    "Permite que este acorde tenha precedência sobre mapeamentos simples durante sua janela.",
  "games.saveChord": "Salvar acorde",
  "games.conflictDiagnostics": "Diagnóstico de conflitos",
  "games.conflictDiagnosticsHelp":
    "Evidência apenas pelo nome do processo; o DS5Forge nunca encerra nem reconfigura outros programas.",
  "games.possibleInputConflict": "Possível conflito de entrada",
  "games.possibleInputConflictBody":
    "Um remapeador ou processo da Steam está em execução. A configuração ativa de entrada não foi inferida.",
  "games.notDetected": "não detectado",
  "games.runtimeLoading": "Carregando runtime",
  "games.pending": "pendente",
  "controller.lightbarIntensity": "Intensidade RGB",
  "controller.lightbarIntensityHelp":
    "Ajusta a intensidade da barra de luz RGB. A intensidade RGB é separada dos LEDs de jogador.",
  "controller.playerLeds": "LEDs de jogador",
  "controller.playerLedsHelp":
    "A saída dos LEDs de jogador é um controle separado da barra de luz RGB e mantém seu próprio estado.",
  "controller.playerLedsEnabled": "LEDs de jogador ativados",
  "controller.playerLedsIntensity": "Intensidade dos LEDs de jogador",
  "controller.calibrationHint":
    "A calibração afeta o espelhamento virtual do modo exclusivo e os metadados de visualização do DS5Forge. A entrada física nativa nunca é alterada.",
  "exclusive.title": "Entrada exclusiva",
  "exclusive.unavailable": "Indisponível até comprovar a origem do provedor e a validação no Windows.",
};

export const dictionaries: Record<Locale, Dictionary> = {
  "en-US": english,
  "pt-BR": portuguese,
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function readLocale(): Locale {
  if (typeof window === "undefined") return "en-US";
  try {
    const value = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return isLocale(value) ? value : "en-US";
  } catch {
    return "en-US";
  }
}

export function persistLocale(locale: Locale): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Private browsing or a locked-down shell can reject localStorage. The
    // active React state remains the source for the current session.
  }
  document.documentElement.lang = locale;
}

export function translate(locale: Locale, key: TranslationKey): string {
  return dictionaries[locale][key];
}

export interface I18nValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: TranslationKey) => string;
}

function useLocalI18n(): I18nValue {
  const [locale, setLocaleState] = useState<Locale>(() => readLocale());
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    persistLocale(next);
  }, []);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const t = useCallback((key: TranslationKey) => translate(locale, key), [locale]);
  return useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
}

const I18nContext = createContext<I18nValue | null>(null);

/**
 * Single app-global locale store. Changing the language here immediately
 * updates every mounted consumer without a reload while keeping offline,
 * first-paint-safe local persistence.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const value = useLocalI18n();
  return createElement(I18nContext.Provider, { value }, children);
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  // Falling back to a local store keeps isolated component tests usable while
  // the real application always renders under I18nProvider.
  const local = useLocalI18n();
  return context ?? local;
}
