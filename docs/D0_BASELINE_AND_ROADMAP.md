# DS5Forge — D0 Baseline & Roadmap

## 1. Objetivo

DS5Forge nasce como uma evolução do projeto open source `Casliyan/DS5companion`, não como uma reimplementação do zero.

Upstream: https://github.com/Casliyan/DS5companion
Licença upstream: MIT — Copyright (c) 2026 Casliyan.

O objetivo do DS5Forge é transformar o baseline funcional existente em uma experiência de DualSense para Windows muito mais completa, confiável e agradável, preservando o que já funciona e evoluindo por camadas verificáveis.

## 2. Restrição de escopo atual

**P0–P4 são 100% focados em conexão USB com fio.**

Fora de escopo nesta fase:
- Bluetooth;
- wireless direto;
- dongles/adaptadores wireless;
- otimizações específicas de transporte Bluetooth;
- paridade wireless com recursos disponíveis por USB.

Esses temas ficam deliberadamente para uma fase posterior.

## 3. Baseline upstream

O DS5Companion atual já entrega uma base funcional importante:
- conexão com DualSense por `pydualsense`;
- captura do áudio padrão do Windows via WASAPI loopback (`PyAudioWPatch`);
- conversão de frequências/envelopes de áudio em rumble;
- touchpad como mouse;
- gestos básicos de um/dois dedos;
- L3/R3 como botões de mouse;
- botão de microfone como toggle;
- configurações persistentes;
- perfis de haptics;
- GUI desktop em `customtkinter`;
- empacotamento atual via PyInstaller.

### Limitações arquiteturais do baseline

- UI e runtime do hardware vivem no mesmo processo e estão fortemente acoplados.
- `AppState` é estado mutável compartilhado diretamente por threads.
- não existe contrato de API local;
- não existe canal WebSocket para telemetria/comandos em tempo real;
- não existe frontend web reutilizável;
- não existe suíte de testes relevante;
- exceções importantes são frequentemente engolidas;
- diagnóstico e logging são insuficientes;
- lifecycle/reconnect dependem de polling e sleeps fixos;
- não há modelo explícito de capabilities do controller;
- não há separação formal entre engine, domínio, infraestrutura e apresentação;
- empacotamento/installer ainda não é uma experiência de produto madura.

## 4. Arquitetura alvo

### 4.1 Core local Windows

Um serviço local será a autoridade para:
- descobrir/conectar o DualSense USB;
- ler input e telemetria;
- enviar output ao controller;
- executar haptics/audio processing;
- executar touchpad/gestures;
- gerenciar perfis e configurações;
- expor capabilities;
- fornecer diagnóstico e health state.

O core deve continuar aproveitando inicialmente a implementação Python funcional do upstream. Migração de partes críticas para Rust/C++ só será considerada se medições reais justificarem.

### 4.2 API local

O core exporá uma API local versionada para comandos e leitura de estado.

Diretrizes:
- HTTP para comandos/configurações não contínuas;
- WebSocket para estado/telemetria/eventos em tempo real;
- bind local seguro por padrão;
- contratos tipados e versionados;
- frontend nunca acessa diretamente `pydualsense` ou objetos internos do runtime.

### 4.3 Frontend

Frontend novo, PC-first e responsivo, compartilhado entre:
- navegador local;
- desktop app instalável;
- acesso remoto controlado via Cloudflare Tunnel;
- uso mobile como painel remoto quando necessário.

A UI deve parecer uma aplicação nativa de PC, não um painel administrativo genérico.

### 4.4 Desktop shell

O shell desktop deve reutilizar o mesmo frontend web e conversar com o mesmo core local. A escolha final do empacotador deve preservar:
- installer simples;
- inicialização/encerramento coordenado do core;
- system tray;
- auto-start opcional;
- atualização futura;
- footprint razoável.

## 5. Princípios do produto

1. USB/wired primeiro.
2. Não quebrar recursos nativos de jogos que já suportam DualSense.
3. Recursos artificiais/compatibilidade devem ser opt-in e transparentes.
4. Reconnect deve ser automático e previsível.
5. Toda configuração importante deve ser persistente e reversível.
6. Nenhuma feature de hardware entra sem diagnóstico e estado observável.
7. O frontend é cliente do core, nunca a autoridade de hardware.
8. Perfis devem evoluir para automação por jogo, mas sem tornar o runtime frágil.
9. Mudanças de DSP/haptics precisam de testes determinísticos e benchmarks.
10. P0–P4 não devem introduzir Bluetooth/wireless por acidente.

## 6. Roadmap em seis sprints grandes

### P0 — Foundation / Core Authority

Objetivo: transformar o fork em uma base sustentável sem perder o comportamento funcional atual.

Escopo:
- importar e preservar o baseline upstream + atribuição MIT;
- remover binário compilado do código-fonte versionado quando apropriado;
- separar `core`, `domain`, `platform/windows` e `presentation`;
- criar lifecycle explícito do controller USB;
- modelar connection state e capabilities;
- substituir estado global solto por snapshots/eventos thread-safe;
- manter haptics WASAPI e touchpad funcionando;
- logging estruturado e IDs de erro;
- config/profile repository versionado;
- health/diagnostics internos;
- API HTTP local inicial;
- WebSocket local inicial;
- testes unitários para DSP, config, state transitions e touch gestures;
- smoke test Windows/USB documentado;
- CI básica para lint/test/build.

Gate P0:
- controller USB conecta/reconecta sem restart manual;
- haptics e touchpad mantêm regressão zero frente ao baseline;
- frontend/clients conseguem observar estado por WebSocket;
- core funciona headless;
- testes automatizados cobrindo regras críticas;
- nenhuma feature Bluetooth/wireless adicionada.

### P1 — PC-first UX / Web + Desktop

Objetivo: substituir a GUI `customtkinter` por uma interface moderna e reutilizável.

Escopo:
- frontend TypeScript moderno;
- shell desktop;
- Overview do controller;
- status de conexão e capabilities;
- bateria/telemetria disponível por USB;
- painel de Haptics;
- painel de Touchpad;
- Profiles;
- Settings;
- Diagnostics;
- realtime via WebSocket;
- loading/error/offline/reconnect states explícitos;
- responsividade para mobile sem comprometer a experiência PC;
- tema dark premium como padrão, com acessibilidade básica.

Gate P1:
- fluxo principal completo sem depender da GUI legada;
- desktop app e browser usam o mesmo frontend;
- reconnect do backend não exige reload manual da UI;
- estados inválidos/desconectados nunca parecem sucesso.

### P2 — Controller Lab / DualSense Depth

Objetivo: aproveitar melhor os recursos físicos do DualSense conectado por USB.

Escopo:
- input monitor em tempo real;
- lightbar controls;
- adaptive trigger lab;
- presets e preview de trigger effects;
- touchpad/gesture editor melhorado;
- calibração/deadzone/visualização de sticks quando suportado;
- haptics test bench;
- perfis completos por controller/configuração;
- capabilities gating para qualquer recurso dependente de hardware;
- import/export de perfis.

Gate P2:
- todo recurso de hardware possui preview/teste, reset e fallback seguro;
- mudanças são aplicadas e revertidas sem reiniciar o app;
- UI só habilita recursos realmente suportados pelo controller/runtime.

### P3 — Compatibility / Games / Automation

Objetivo: transformar DS5Forge em uma camada prática para jogos com diferentes níveis de suporte ao DualSense.

Escopo:
- detecção de processo/jogo em foreground;
- auto-profile por jogo;
- remapping e chords;
- modos de compatibilidade claramente separados do modo nativo;
- opção de virtual gamepad/XInput caso a solução escolhida seja tecnicamente segura e sustentável;
- prevenção de double input quando um virtual device estiver ativo;
- regras de ativação/desativação por jogo;
- restauração segura ao fechar/trocar jogo;
- diagnóstico de conflitos com Steam Input/outros remappers.

Gate P3:
- modo nativo continua sendo o default;
- compatibilidade nunca é ativada silenciosamente;
- saída virtual/desvio de input possui teardown determinístico;
- trocar ou fechar jogo não deixa teclas/botões virtuais presos.

### P4 — Productization / Release / Remote Control

Objetivo: tornar o DS5Forge instalável, atualizável e utilizável como produto de PC.

Escopo:
- installer Windows;
- desktop packaging definitivo;
- system tray;
- auto-start opcional;
- single-instance;
- crash recovery;
- update strategy;
- logs exportáveis;
- diagnóstico guiado;
- CI/CD e releases versionadas;
- assinatura futura preparada;
- exposição segura do frontend via Cloudflare Tunnel;
- WebSocket funcionando através do tunnel;
- acesso remoto/mobile como painel de controle;
- autenticação/controle de origem apropriados antes de exposição externa.

Gate P4:
- instalação limpa em Windows suportado;
- start/stop/uninstall previsíveis;
- nenhuma porta externa aberta por padrão;
- tunnel remoto é opt-in;
- release reproduzível por CI;
- documentação de troubleshooting e recovery.

### P5 — Compatibility / Game Intelligence / UX Stabilization

P5 preserves Native as the default and keeps the USB/wired-only boundary. It
adds a capability-gated Exclusive coordinator, investigated through a fixed
HIDMaestro + HidHide helper boundary, without installing a provider or adding
ViGEmBus. The coordinator mirrors complete state, owns token/generation/
heartbeat cleanup and rolls back if virtual output or physical suppression
fails. `double_input_risk=true` remains visible until suppression and Windows
validation are proven.

P5 also separates adaptive-trigger arbitration from Controller Lab, adds
running/recent game candidates and a native executable picker, stabilizes stale
topbar/profile/mode trust states, adds typed offline `pt-BR`/`en-US` i18n and
first-paint theme bootstrap, keeps Remote Access under Settings → Advanced,
and separates RGB lightbar intensity from Player LEDs. See
[`P5_UX_SPEC.md`](P5_UX_SPEC.md),
[`ADR_P5_EXCLUSIVE_INPUT_PROVIDER.md`](ADR_P5_EXCLUSIVE_INPUT_PROVIDER.md) and
[`P5_VALIDATION.md`](P5_VALIDATION.md).

Gate P5:

- Python/frontend source gates and contract tests are green;
- Tauri/Rust checks pass on the native Windows toolchain;
- no Bluetooth/wireless/provider installation is introduced;
- real Windows/provider, physical DualSense, game, WASAPI loopback and
  packaged lifecycle evidence is separately recorded, otherwise the handoff
  remains `WINDOWS/HARDWARE VALIDATION PENDING`.

## 7. D0 — ponto de partida

D0 não é uma sprint de feature. É o marco de preparação antes da execução P0.

D0 está pronto quando:
- [ ] upstream e licença estão documentados;
- [ ] snapshot fonte do upstream está disponível no repositório DS5Forge;
- [ ] remote `origin` aponta para `vinileonardo/DS5Forge`;
- [ ] remote `upstream` aponta para `Casliyan/DS5companion`;
- [ ] README do DS5Forge deixa claro o escopo wired-first;
- [ ] roadmap P0–P5 está versionado;
- [ ] instruções para agentes estão versionadas;
- [ ] baseline pode ser instalado/executado no Windows a partir do source;
- [ ] smoke checklist inicial existe;
- [ ] nenhuma alteração funcional relevante foi feita antes do baseline ser registrado.

## 8. Critério para começar desenvolvimento delegado

Depois do D0, cada sprint será executada em bloco grande por uma IA de implementação seguindo um Execution Pack. O code review independente acontecerá depois de blocos grandes, no mesmo estilo usado no Fitzi.

A IA implementadora não recebe liberdade para mudar o escopo wireless-first/wired-first, trocar a arquitetura inteira por preferência pessoal, ou introduzir dependências de driver sem ADR e justificativa técnica.
