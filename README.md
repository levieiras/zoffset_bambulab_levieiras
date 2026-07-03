# Z-Offset Tool — Bambu Lab A1

Ferramenta para aplicar z-offset personalizado em arquivos `.gcode.3mf` para múltiplas impressoras Bambu Lab A1.

## O problema

Quando se trabalha com várias impressoras Bambu Lab A1, cada uma acaba tendo um valor ideal de z-offset — aquela microajuste na distância entre a ponta da extrusora e a mesa de impressão que faz a primeira camada sair perfeita. O problema é que a Bambu Lab **não permite editar esse valor por impressora**. O z-offset fica fixo dentro do arquivo fatiado (`.gcode.3mf`), e quando você fatia um projeto, não sabe exatamente em qual impressora ele vai rodar.

O resultado? Você acaba tendo que **fatiar o mesmo arquivo N vezes** — uma para cada impressora — só para ajustar esse valor. Trabalho duplicado, ineficiente e propício a erros.

## A solução

Esta ferramenta resolve isso de forma simples: você fatia o arquivo **uma única vez** com um z-offset genérico, joga na pasta `to_process/`, e o script gera automaticamente **uma cópia para cada impressora** já com o z-offset correto aplicado.

```
to_process/
├── patolino.gcode.3mf          ← arquivo fatiado uma vez

         ↓ Processa para todas as impressoras ↓

ready/
├── patolino_A1-Sala.3mf        ← z-offset: -0.02mm
├── patolino_A1-Quarto.3mf      ← z-offset: +0.01mm
├── patolino_A1-Escritorio.3mf  ← z-offset: -0.03mm
├── patolino_A1-Garagem.3mf     ← z-offset: +0.00mm
└── patolino_A1-Oficina.3mf     ← z-offset: -0.01mm
```

O que antes era um processo manual chato e repetitivo agora é **um único comando**.

## Como funciona por baixo dos panos

O arquivo `.gcode.3mf` é na verdade um arquivo ZIP contendo o G-code fatiado. Dentro dele, o z-offset está definido no comando `G29.1 Z{valor}`. O script:

1. Abre o arquivo `.3mf` como um ZIP
2. Localiza o comando `G29.1 Z` no G-code de cada placa
3. Substitui pelo z-offset da impressora correspondente
4. Recalcula o checksum MD5 (obrigatório para o arquivo ser válido)
5. Gera um novo arquivo `.3mf` para cada impressora

Tudo isso sem dependências externas — apenas Python padrão.

## Requisitos

- Python 3.10 ou superior
- Sem dependências externas (usa apenas bibliotecas padrão do Python)

## Instalação

```bash
git clone https://github.com/levieiras/zoffset_bambulab_levieiras.git
cd zoffset_bambulab_levieiras
```

## Configuração

Copie o arquivo de exemplo e edite com suas impressoras:

```bash
cp printers.example.json printers.json
```

Edite `printers.json` com seus z-offsets ideais:

```json
{
    "imp1": {
        "name": "A1-01",
        "z_offset": -0.02
    },
    "imp2": {
        "name": "A1-02",
        "z_offset": 0.01
    },
    "imp3": {
        "name": "A1-03",
        "z_offset": -0.03
    }
}
```

| Campo | Descrição |
|-------|-----------|
| `name` | Nome da impressora (usado no nome do arquivo de saída) |
| `z_offset` | Valor de z-offset em mm (negativo = mais perto da mesa) |

> **Dica:** O valor de `z_offset` pode ser positivo ou negativo. Use valores pequenos (décimos de milímetro). Se não sabe o valor ideal da sua impressora, faça um teste com uma folha de papel ajustando o valor até a primeira camada sair uniforme.

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

## Estrutura do projeto

```
zoffset_bambulab_levieiras/
├── to_process/                  # Coloque seus .3mf aqui
├── ready/                       # Arquivos gerados (nao versionados)
├── printers.example.json        # Template de configuracao
├── printers.json                # Sua configuracao (nao versionado)
├── zoffset_tool.py              # Script principal
├── README.md                    # Este arquivo
└── .gitignore
```

## Notas

- Arquivos já processados (com `_` no nome da impressora) são ignorados em execuções futuras
- O script funciona com arquivos de placa única e múltiplas placas
- O checksum MD5 é recalculado automaticamente para validade do arquivo
- Os arquivos de saída são cópias — o original não é modificado

## Licença

MIT
