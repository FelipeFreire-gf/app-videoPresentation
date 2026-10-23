# Video Presentation

Aplicativo de terminal que reproduz um vídeo **em loop** numa janela de tamanho
customizável, com um texto sobreposto. Nada é salvo — o texto é desenhado em tempo real.

## Requisitos

- Python 3
- ffmpeg (fornece `ffplay` e `ffprobe`) — no Arch: `sudo pacman -S ffmpeg`

## Uso

```bash
./video_presentation.py            # pergunta o caminho do vídeo
./video_presentation.py meu.mp4    # já começa com o vídeo escolhido
```

O app pergunta, no terminal:

1. Caminho do vídeo (TAB autocompleta)
2. Texto (várias linhas permitidas; linha vazia termina)
3. Timer: regressivo ou progressivo, duração em segundos e onde mostrar
   (ao lado, abaixo ou acima do texto). Abaixo de 60 s mostra só os segundos
   (`50`, `49`...); acima disso mostra em minutos (`1:30`).
4. Largura e altura da janela
5. Tamanho da fonte, cor, posição, fundo atrás do texto e se quer som

As escolhas são feitas em menus interativos: `↑`/`↓` (ou `j`/`k`) para mover,
`Enter` para confirmar, ou o número da opção. O timer não reinicia quando o vídeo
volta ao início, e continua contando mesmo com o vídeo pausado.

Atalhos na janela do vídeo: `q`/`ESC` fecha, `f` tela cheia, `espaço` pausa,
`←`/`→` volta/avança. A janela também pode ser redimensionada com o mouse.

Ao fechar a janela, um menu permite reproduzir de novo, mudar o texto, a janela,
o estilo ou escolher outro vídeo.
