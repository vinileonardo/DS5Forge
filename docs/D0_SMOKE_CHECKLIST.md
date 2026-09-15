# DS5Forge — D0 Windows/USB Smoke Checklist

Este checklist registra o comportamento mínimo do upstream que deve existir antes de iniciar a refatoração P0 e deve ser repetido sempre que o core de hardware for alterado.

## Ambiente

- Windows 10/11 suportado;
- DualSense conectado **por cabo USB**;
- saída de áudio padrão do Windows configurada para speakers/headset normal;
- Python e dependências do baseline instalados quando executando a partir do source;
- nenhum teste Bluetooth/wireless faz parte deste checklist.

## Instalação baseline

- [ ] criar ambiente virtual limpo;
- [ ] instalar `source/requirements.txt` sem erro fatal;
- [ ] iniciar o app a partir do source;
- [ ] app abre sem exigir Bluetooth;
- [ ] config inicial é criada/carregada corretamente;
- [ ] perfis default são encontrados.

## Controller lifecycle

- [ ] app inicia sem controller e permanece estável aguardando conexão;
- [ ] conectar DualSense USB depois do app aberto é detectado;
- [ ] status muda para conectado;
- [ ] desconectar o cabo não derruba o processo;
- [ ] motores são neutralizados no disconnect quando possível;
- [ ] reconectar o cabo volta ao estado conectado sem restart do app;
- [ ] fechar o app encerra threads/processos relacionados.

## Audio-driven rumble

- [ ] WASAPI loopback identifica a saída padrão;
- [ ] áudio do Windows continua saindo normalmente pelos speakers/headset;
- [ ] reprodução de áudio compatível gera rumble;
- [ ] silêncio/áudio abaixo do gate não gera vibração residual relevante;
- [ ] desligar rumble na UI zera ambos os motores;
- [ ] reativar rumble volta a responder;
- [ ] trocar parâmetros principais produz efeito perceptível;
- [ ] botão de teste gera feedback e termina sozinho;
- [ ] trocar dispositivo de áudio padrão não exige reiniciar todo o app.

## Touchpad / mouse

- [ ] um dedo move o cursor;
- [ ] tap de um dedo gera clique esquerdo;
- [ ] dois dedos fazem scroll vertical;
- [ ] tap de dois dedos gera clique direito;
- [ ] click físico do touchpad gera clique conforme baseline;
- [ ] L3/R3 preservam comportamento atual do baseline;
- [ ] desabilitar trackpad interrompe movimento/cliques sintéticos;
- [ ] reabilitar trackpad volta a funcionar;
- [ ] desconectar/fechar não deixa botão de mouse logicamente pressionado.

## Mic button toggle

- [ ] comportamento configurado (`master`, `rumble` ou `trackpad`) funciona;
- [ ] feedback do toggle termina sozinho;
- [ ] estados exibidos pela UI correspondem ao runtime.

## Profiles/config

- [ ] carregar `Default` funciona;
- [ ] carregar presets upstream funciona;
- [ ] salvar configuração persiste após restart;
- [ ] perfil novo pode ser salvo/carregado;
- [ ] config inválida/corrompida produz erro compreensível ou fallback seguro, sem enviar valores arbitrários ao hardware.

## Evidências D0

Registrar no review D0/P0:
- versão do Windows;
- modelo/firmware do controller quando disponível;
- método de execução (source/build);
- PASS/FAIL por seção;
- logs/erro para qualquer FAIL;
- diferenças conhecidas em relação ao upstream.

## Gate

P0 não deve alegar regressão zero do baseline sem este checklist ou testes automatizados equivalentes para o comportamento alterado.

## Registro P0

- [x] gates automatizados registrados em `docs/P0_VALIDATION.md`;
- [x] API `/api/v1/health`, `/state`, config e comandos testados em loopback;
- [x] WebSocket recebe snapshot inicial e evento de mudança;
- [x] nenhuma referência de hardware é exposta pela GUI/API;
- [x] shutdown deixa threads, motores e botões sintéticos em estado neutro nos testes automatizados/fakes;
- [x] Windows + DualSense USB físico permanece explicitamente como `HARDWARE VALIDATION PENDING`;
- [x] auditoria de código confirma que P0 não adicionou Bluetooth/wireless.

## Registro P1 — browser/Tauri

Estas verificações cobrem a nova apresentação e não substituem a validação
física Windows + DualSense USB acima.

- [ ] iniciar `python source/run.py --headless` e `npm run dev` em terminais separados;
- [ ] abrir `http://127.0.0.1:5173` e confirmar Overview, status do core e estado do controller;
- [ ] confirmar que core offline aparece como offline/reconnecting e recupera sem reload;
- [ ] confirmar que Overview, Haptics, Touchpad, Profiles, Diagnostics e Settings são navegáveis por teclado;
- [ ] confirmar que Haptics/Touchpad aguardam confirmação do core e exibem 422 estruturado;
- [ ] confirmar que perfis bundled são read-only e exclusão user exige confirmação;
- [ ] confirmar que o preview do frontend e o Tauri usam a mesma SPA;
- [ ] confirmar que origins remotas, wildcard CORS e bind externo são rejeitados;
- [ ] confirmar que nenhum recurso P2/P3/P4 ou Bluetooth/wireless aparece como caminho ativo.

## Registro P2 — Controller Lab

Estas verificações cobrem a extensão Controller Lab e continuam exigindo um
DualSense real conectado por cabo USB. Testes automatizados/frontend devem ser
registrados separadamente em `docs/P2_VALIDATION.md`.

- [ ] abrir `/controller` e confirmar as abas Input, Triggers, Lighting e Sticks;
- [ ] Input mostra botões, D-pad, L2/R2, dois sticks e pontos de toque sem expor objeto Windows;
- [ ] desconectar durante a tela mostra estado stale/offline e desabilita comandos de saída;
- [ ] reconectar atualiza snapshot sem reload e inicia com motores/gatilhos em estado neutro;
- [ ] aplicar/resetar lightbar funciona quando a capability é reportada;
- [ ] trigger preview expira e reseta ambos os gatilhos para Off;
- [ ] cancelar preview, desconectar e fechar o app também reseta os gatilhos;
- [ ] haptics test respeita duração máxima, bloqueia duplicata e termina com motores zerados;
- [ ] ajustar gestos/pontos do touchpad preserva release de botões sintéticos no teardown;
- [ ] salvar/exportar/importar perfil v2 funciona; overwrite exige confirmação;
- [ ] perfil bundled continua read-only e capability ausente aparece como motivo explícito;
- [ ] deadzone/calibration é apresentado como metadata de visualização DS5Forge, sem alterar input nativo do jogo.

## Gate P2

- [x] gates automatizados e limitações registrados em `docs/P2_VALIDATION.md`;
- [x] auditoria de fronteira confirma que a UI não importa `pydualsense`, WASAPI ou APIs HID;
- [x] auditoria USB-only confirma que P2 não adicionou Bluetooth, pairing ou transporte wireless;
- [ ] Windows + DualSense USB físico: permanece `HARDWARE VALIDATION PENDING` até evidência real ser anexada.

## Registro P3 — Games / compatibility / automation

Estas verificações continuam exigindo Windows e um DualSense conectado por
USB. A UI e os testes com fakes não substituem a prova física.

- [ ] abrir `/games` sem jogo em foreground e confirmar `No active game`;
- [ ] confirmar foreground com nome do executável, PID, título e timestamp;
- [ ] cadastrar uma regra por nome de executável e confirmar `Test match` com razão;
- [ ] habilitar automation e confirmar aplicação automática do perfil no jogo;
- [ ] trocar jogo A → jogo B e confirmar que a nova regra/profile é aplicada;
- [ ] fechar o jogo ou voltar ao desktop e confirmar a política selecionada;
- [ ] verificar `restore_previous` (default), `apply_default` e `keep_current`;
- [ ] alterar profile/mode manualmente e confirmar manual override até transição real;
- [ ] configurar mapping simples e chord; confirmar precedência, debounce e release;
- [ ] confirmar mapping de mouse left/right/middle e Mouse4/Mouse5, incluindo release após teardown;
- [ ] desconectar/reconectar, trocar mode/profile e fechar o app; confirmar que
  nenhuma tecla/botão sintético fica pressionado;
- [ ] confirmar Native como default e Remap apenas quando explicitamente escolhido;
- [ ] confirmar Virtual/XInput como `Unavailable` sem provider aprovado e sem
  mudança silenciosa do mode;
- [ ] confirmar aviso de Steam/remapper como possibilidade baseada apenas em
  nome de processo, sem matar/reconfigurar software externo;
- [ ] quando enumeração de processos estiver indisponível, confirmar que a UI
  informa que não foi possível inspecionar em vez de afirmar que o processo não existe;
- [ ] validar foreground de um jogo/processo que permita apenas query limitada e
  confirmar que o caminho/nome do executável ainda é obtido sem exigir VM_READ;
- [ ] confirmar que a página atualiza active game por WebSocket sem reload.

## Gate P3

- [x] contratos, registry separado, foreground worker, remapping, compatibility
  gating e Games UI implementados para revisão independente;
- [x] Virtual/XInput permanece indisponível em produção por decisão técnica;
- [x] nenhuma implementação Bluetooth/wireless, driver, installer ou nova
  permissão Tauri adicionada;
- [ ] Windows foreground/SendInput e DualSense USB físico permanecem
  `HARDWARE VALIDATION PENDING` até evidência real ser anexada.
