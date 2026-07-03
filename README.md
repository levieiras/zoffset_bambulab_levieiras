# Z-Offset Tool — Bambu Lab A1

Ferramenta para aplicar z-offset personalizado em arquivos `.gcode.3mf` para impressoras 3D Bambu Lab A1.

## Problema

Cada impressora Bambu Lab A1 tem um valor ideal de z-offset, mas o Bambu Lab Studio não permite editar esse valor por impressora — ele fica fixo no arquivo fatiado (`.gcode.3mf`). Quando você fatia um arquivo, não sabe em qual impressora ele vai rodar.

## Solução

Esta ferramenta modifica o z-offset diretamente no G-code dentro do arquivo `.3mf`, gerando uma cópia para cada impressora com o valor correto.

```
to_process/
├── patolino.gcode.3mf

         ↓ Processa para 5 impressoras ↓

ready/
├── patolino_A1-Sala.3mf       (z-offset: -0.02mm)
├── patolino_A1-Quarto.3mf     (z-offset: +0.01mm)
├── patolino_A1-Escritorio.3mf (z-offset: -0.03mm)
├── patolino_A1-Garagem.3mf    (z-offset: +0.00mm)
└── patolino_A1-Oficina.3mf    (z-offset: -0.01mm)
```

## Requisitos

- Python 3.10 ou superior
- Sem dependências externas (usa apenas bibliotecas padrão do Python)

## Instalação

```bash
git clone https://github.com/levieiras/zoffset_bambulab_levieiras.git
cd zoffset_bambulab_levieiras
```

## Configuração

Edite o arquivo `printers.json` com suas impressoras e z-offsets ideais:

```json
{
    "imp1": {
        "name": "A1 - Sala",
        "z_offset": -0.02
    },
    "imp2": {
        "name": "A1 - Quarto",
        "z_offset": 0.01
    },
    "imp3": {
        "name": "A1 - Escritorio",
        "z_offset": -0.03
    }
}
```

| Campo | Descrição |
|-------|-----------|
| `name` | Nome da impressora (usado no nome do arquivo de saída) |
| `z_offset` | Valor de z-offset em mm (negativo = mais perto da mesa) |

## Uso

### Modo lote (recomendado)

Coloque seus arquivos `.gcode.3mf` na pasta `to_process/` e execute:

```bash
python zoffset_tool.py to_process
```

Os arquivos gerados ficam na pasta `ready/`.

### Modo interativo

```bash
python zoffset_tool.py
```

O menu permite:
1. Selecionar uma impressora específica ou todas
2. Informar o caminho de um arquivo ou pasta

## Como funciona

1. O arquivo `.gcode.3mf` é um arquivo ZIP contendo o G-code fatiado
2. O z-offset está no comando `G29.1 Z{valor}` dentro do G-code
3. O script substitui esse valor e recalcula o checksum MD5
4. Gera um novo arquivo `.3mf` para cada impressora

## Estrutura do projeto

```
zoffset_bambulab_levieiras/
├── to_process/          # Coloque seus .3mf aqui
├── ready/               # Arquivos gerados (nao versionados)
├── printers.json        # Configuracao das impressoras
├── zoffset_tool.py      # Script principal
├── README.md            # Este arquivo
└── .gitignore
```

## Notas

- Arquivos já processados (com `_` no nome da impressora) são ignorados em execuções futuras
- Um backup do original não é criado — os arquivos de saída são cópias
- O script funciona com arquivos de placa única e múltiplas placas
- O checksum MD5 é recalculado automaticamente para validade do arquivo

## Licença

MIT
