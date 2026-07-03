#!/usr/bin/env python3
"""
Z-Offset Tool — Bambu Lab A1
Aplica z-offset personalizado em arquivos .gcode.3mf.

Sem dependencias externas — usa apenas bibliotecas padrao do Python.

Uso:
  python zoffset_tool.py                        # Menu interativo
  python zoffset_tool.py caminho/pasta/         # Modo lote: processa toda a pasta
"""

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "printers.json"


# ════════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════════

def load_printers():
    """Carrega configuracao de impressoras do JSON."""
    example_file = SCRIPT_DIR / "printers.example.json"

    if not CONFIG_FILE.exists():
        if example_file.exists():
            print(f"\n  Arquivo printers.json nao encontrado.")
            print(f"  Copie o exemplo para criar sua configuracao:\n")
            print(f"    cp printers.example.json printers.json\n")
            print(f"  Depois edite printers.json com seus z-offsets reais.")
        else:
            print(f"\n  Erro: {CONFIG_FILE.name} nao encontrado.")
            print("  Crie o arquivo printers.json com as impressoras e z-offsets.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("  Erro: printers.json esta vazio.")
        sys.exit(1)

    return data


# ════════════════════════════════════════════════════════════════════════
#  3MF / ZIP HANDLING
# ════════════════════════════════════════════════════════════════════════

def md5_hex(data_bytes):
    """Calcula MD5 hex digest de bytes."""
    return hashlib.md5(data_bytes).hexdigest()


def find_plate_gcode_files(zip_file):
    """
    Encontra todos os arquivos de gcode de placa dentro do ZIP.
    Retorna lista de tuplas (nome_no_zip, conteudo_bytes).
    """
    plates = []
    for name in zip_file.namelist():
        # Padr: Metadata/plate_1.gcode, Metadata/plate_2.gcode, etc.
        if re.match(r'.*Metadata/plate_\d+\.gcode$', name):
            content = zip_file.read(name)
            plates.append((name, content))
    return plates


def find_md5_file(zip_file, gcode_name):
    """Encontra o arquivo MD5 correspondente ao gcode."""
    md5_name = gcode_name + ".md5"
    if md5_name in zip_file.namelist():
        return md5_name
    return None


def replace_z_offset(gcode_bytes, new_offset):
    """
    Substitui G29.1 Z{valor} pelo novo z-offset no G-code.

    Procura por linhas como:
      G29.1 Z-0.02
      G29.1 Z+0.01
      G29.1 Z0.03

    Retorna (gcode_modificado_bytes, quantidade_substituicoes).
    """
    gcode_str = gcode_bytes.decode("utf-8", errors="replace")

    # Padrao: G29.1 seguido de Z com sinal opcional e numero
    pattern = r'(G29\.1\s+Z)[+-]?\d+\.?\d*'

    count = [0]

    def replacer(match):
        count[0] += 1
        return f"{match.group(1)}{new_offset:+.2f}"

    new_gcode_str = re.sub(pattern, replacer, gcode_str, flags=re.IGNORECASE)
    new_gcode_bytes = new_gcode_str.encode("utf-8")

    return new_gcode_bytes, count[0]


def repack_3mf(input_path, output_path, modifications):
    """
    Reempacota o arquivo 3MF com as modificacoes.

    modifications: dict {nome_arquivo_no_zip: novo_conteudo_bytes}
    """
    # Copiar arquivo original como base
    shutil.copy2(input_path, output_path)

    with zipfile.ZipFile(output_path, "r", allowZip64=True) as zin:
        # Ler todos os arquivos e suas propriedades
        file_list = []
        for item in zin.infolist():
            if item.filename in modifications:
                new_content = modifications[item.filename]
                file_list.append((item, new_content, True))
            else:
                file_list.append((item, zin.read(item.filename), False))

    # Reescrever o ZIP com os arquivos modificados
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        for item, content, was_modified in file_list:
            # Criar novo InfoItem preservando metadados originais quando possivel
            info = zipfile.ZipInfo(item.filename)
            info.date_time = item.date_time
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr

            zout.writestr(info, content)


# ════════════════════════════════════════════════════════════════════════
#  PROCESSAMENTO
# ════════════════════════════════════════════════════════════════════════

def sanitize_name(name):
    """Torna um nome seguro para uso em nomes de arquivo."""
    # Substituir espacos e caracteres especiais por hifens
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', name)
    # Remover hifens duplos
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remover hifens no inicio e fim
    return sanitized.strip('-')


def process_file(input_path, printers, output_dir):
    """
    Processa UM arquivo .gcode.3mf para TODAS as impressoras.
    Retorna lista de (nome_arquivo, sucesso, detalhe).
    """
    results = []

    for printer_key, printer_info in printers.items():
        printer_name = printer_info["name"]
        z_offset = printer_info["z_offset"]

        suffix = sanitize_name(printer_name)
        output_name = f"{input_path.stem}_{suffix}.3mf"
        output_path = output_dir / output_name

        try:
            with zipfile.ZipFile(input_path, "r", allowZip64=True) as zf:
                plate_files = find_plate_gcode_files(zf)

                if not plate_files:
                    results.append((output_name, False, "Nenhum plate gcode encontrado"))
                    continue

                modifications = {}
                total_replacements = 0

                for gcode_name, gcode_content in plate_files:
                    new_gcode, count = replace_z_offset(gcode_content, z_offset)
                    total_replacements += count

                    if count > 0:
                        modifications[gcode_name] = new_gcode

                        # Recomputar MD5
                        md5_name = find_md5_file(zf, gcode_name)
                        if md5_name:
                            new_md5 = md5_hex(new_gcode).encode("utf-8")
                            modifications[md5_name] = new_md5

                if total_replacements == 0:
                    results.append((output_name, False, "G29.1 nao encontrado no gcode"))
                    continue

                # Reempacotar
                repack_3mf(input_path, output_path, modifications)

                results.append((
                    output_name,
                    True,
                    f"z-offset: {z_offset:+.2f}mm ({total_replacements} placa(s))"
                ))

        except zipfile.BadZipFile:
            results.append((output_name, False, "Arquivo 3MF corrompido ou invalido"))
        except Exception as e:
            results.append((output_name, False, f"Erro: {e}"))

    return results


# ════════════════════════════════════════════════════════════════════════
#  MODO LOTE (PASTA)
# ════════════════════════════════════════════════════════════════════════

def batch_mode(folder_path):
    """Processa todos os .gcode.3mf de uma pasta para todas as impressoras."""
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        print(f"\n  Erro: '{folder}' nao e uma pasta valida.")
        sys.exit(1)

    # Encontrar arquivos .3mf (excluir ja processados com _imp)
    all_3mf = sorted(folder.glob("*.3mf"))
    input_files = [f for f in all_3mf if "_imp" not in f.stem]

    if not input_files:
        print(f"\n  Nenhum arquivo .3mf novo encontrado em '{folder}'.")
        print("  (Arquivos com _imp no nome sao ignorados)")
        sys.exit(1)

    printers = load_printers()

    # Pastas de saida e processados
    output_dir = folder / "ready"
    processed_dir = folder / "processed"
    output_dir.mkdir(exist_ok=True)
    processed_dir.mkdir(exist_ok=True)

    total_files = len(input_files)
    total_printers = len(printers)
    total_expected = total_files * total_printers

    print()
    print("=" * 62)
    print("  Z-OFFSET TOOL — MODO LOTE")
    print("=" * 62)
    print(f"  Pasta entrada:   {folder}")
    print(f"  Arquivos:        {total_files}")
    print(f"  Impressoras:     {total_printers}")
    print(f"  Pasta saida:     {output_dir}")
    print(f"  Pasta originais: {processed_dir}")
    print(f"  Total esperado:  {total_expected} arquivos")
    print("=" * 62)
    print()

    total_ok = 0
    total_fail = 0

    for i, file_path in enumerate(input_files, 1):
        print(f"[{i}/{total_files}] {file_path.name}")

        results = process_file(file_path, printers, output_dir)

        # Verificar se todos foram com sucesso
        all_success = all(success for _, success, _ in results)

        for name, success, detail in results:
            if success:
                print(f"    OK   {name}  ({detail})")
                total_ok += 1
            else:
                print(f"    FALHA {name}  ({detail})")
                total_fail += 1

        # Mover original para processed/ se todos com sucesso
        if all_success:
            dest = processed_dir / file_path.name
            shutil.move(str(file_path), str(dest))
            print(f"    MOVIDO -> processed/{file_path.name}")

        print()

    # Resumo final
    print("=" * 62)
    print("  RESUMO")
    print("=" * 62)
    print(f"  Sucesso:  {total_ok} arquivos gerados")
    if total_fail > 0:
        print(f"  Falha:    {total_fail} arquivos")
    print(f"  Saida:    {output_dir}")
    print(f"  Originais movidos para: {processed_dir}")
    print("=" * 62)
    print()


# ════════════════════════════════════════════════════════════════════════
#  MODO INTERATIVO
# ════════════════════════════════════════════════════════════════════════

def interactive_mode():
    """Menu interativo para processamento."""
    printers = load_printers()
    printer_list = list(printers.items())

    print()
    print("=" * 62)
    print("  Z-OFFSET TOOL — Bambu Lab A1")
    print("  Aplicar z-offset personalizado em .gcode.3mf")
    print("=" * 62)

    # Listar impressoras
    print()
    print("  Impressoras configuradas:")
    print()
    for i, (key, info) in enumerate(printer_list, 1):
        z = info["z_offset"]
        suffix = sanitize_name(info["name"])
        print(f"    [{i}] {info['name']:<25} z-offset: {z:+.2f}mm  (saida: _{suffix})")
    print(f"    [T] Todas as impressoras (modo lote)")
    print(f"    [0] Sair")
    print()

    # Selecionar
    while True:
        choice = input("  Opcao: ").strip().upper()
        if choice == "0":
            print("  Saindo...")
            sys.exit(0)
        if choice == "T":
            selected_printers = printers
            break
        try:
            idx = int(choice)
            if 1 <= idx <= len(printer_list):
                key = printer_list[idx - 1][0]
                selected_printers = {key: printers[key]}
                break
        except ValueError:
            pass
        print("  Opcao invalida. Tente novamente.")

    # Caminho
    print()
    path_input = input("  Caminho do arquivo .3mf ou pasta: ").strip().strip('"')
    path = Path(path_input).resolve()

    if path.is_dir():
        # Pasta — processar todos
        all_3mf = sorted(path.glob("*.3mf"))
        input_files = [f for f in all_3mf if "_imp" not in f.stem]

        if not input_files:
            print(f"\n  Nenhum arquivo .3mf novo encontrado em '{path}'.")
            sys.exit(1)

        output_dir = path / "ready"
        processed_dir = path / "processed"
        output_dir.mkdir(exist_ok=True)
        processed_dir.mkdir(exist_ok=True)

        print(f"\n  {len(input_files)} arquivo(s) encontrado(s). Processando...\n")

        for i, file_path in enumerate(input_files, 1):
            print(f"  [{i}/{len(input_files)}] {file_path.name}")
            results = process_file(file_path, selected_printers, output_dir)

            all_success = all(success for _, success, _ in results)

            for name, success, detail in results:
                tag = "OK" if success else "FALHA"
                print(f"    {tag}  {name}  ({detail})")

            if all_success:
            dest = processed_dir / file_path.name
                shutil.move(str(file_path), str(dest))
                print(f"    MOVIDO -> processed/{file_path.name}")

            print()

        print(f"  Arquivos de saida em: {output_dir}")
        print(f"  Originais movidos para: {processed_dir}")

    elif path.exists() and path.suffix.lower() == ".3mf":
        # Arquivo unico
        output_dir = path.parent
        processed_dir = output_dir / "processed"
        processed_dir.mkdir(exist_ok=True)

        print(f"\n  Processando: {path.name}\n")

        results = process_file(path, selected_printers, output_dir)

        all_success = all(success for _, success, _ in results)

        for name, success, detail in results:
            tag = "OK" if success else "FALHA"
            print(f"  {tag}  {name}  ({detail})")

        if all_success:
            dest = processed_dir / path.name
            shutil.move(str(path), str(dest))
            print(f"\n  MOVIDO -> processed/{path.name}")

        print()

    else:
        print(f"\n  '{path}' nao e um arquivo .3mf ou pasta valida.")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    # Modo lote: passar pasta como argumento
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        batch_mode(sys.argv[1])
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
