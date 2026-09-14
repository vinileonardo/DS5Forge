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
