#!/usr/bin/env python3
"""Convierte saves de Persona 4 Golden (PC/Steam) al formato de PS Vita.

Uso:
    python3 p4g_pc2vita.py P4GoldenPC                      # crea P4GoldenPC_conv/
    python3 p4g_pc2vita.py P4GoldenPC --base-sdslot P4GVita/sce_sys/sdslot.dat

Formato (verificado contra saves reales de Vita y la documentacion de
https://github.com/zarroboogs/p4g-saveconv):
  * dataXXXX.bin: igual en PC y Vita salvo el segmento "rescue requests"
    (0x15120..) y el checksum de 0x3165C. Vita rellena el archivo a 0x38000.
  * system.bin: identico.
  * PC guarda los metadatos en dataXXXX.binslot; Vita los junta en
    sce_sys/sdslot.dat (17 slots de 0x400 bytes desde 0x400). El texto de cada
    slot se reescribe con etiquetas en ingles: con otro idioma la Vita se
    congela en "Load game".
"""
import argparse
import re
import shutil
import struct
import unicodedata
from pathlib import Path

VITA_SIZE = 0x38000
SLOT_SIZE = 0x400
NUM_SLOTS = 17  # slot 0 = system, 1..16 = data0001..data0016
BINSLOT_HEADER = 0x28  # "SAVE0001" + MD5 slot + MD5 bin


def convert_bin(pc: bytes, custom_diff: str = "disable") -> bytes:
    if len(pc) < 0x19D10:
        raise ValueError(f"save PC demasiado pequeno ({len(pc):#x} bytes)")
    name = pc[0x10:0x10 + 0x24]  # nombre en la codificacion propia del juego
    out = bytearray(VITA_SIZE)

    out[0:0x15120] = pc[0:0x15120]
    # flags del menu de dificultad custom (solo existe en PC): bits 0-1 de 0x1304
    if custom_diff == "disable":
        out[0x1304] &= ~0x03 & 0xFF
    elif custom_diff == "enable":
        out[0x1304] |= 0x03
    # nuevo segmento de rescue requests
    struct.pack_into("<2I", out, 0x15120, 0x0000000F, 0x00002900)
    struct.pack_into("<2I", out, 0x15128, 0x4D16009B, 0x4D0F004D)  # mensaje por defecto
    out[0x15130:0x15130 + 0x24] = name
    out[0x15130 + 0x24] = 1
    # resto de segmentos: igual que Vita
    out[0x17A28:0x17A28 + 0xC14] = pc[0x190CC:0x190CC + 0xC14]
    end = 0x17A28 + 0xC14
    # cabeceras de "retry save" vacias
    struct.pack_into("<2II", out, end, 0x10000001, 4, 0)
    struct.pack_into("<2II", out, end + 12, 0x10000002, 4, 0)
    struct.pack_into("<2I", out, end + 24, 0x10000003, 0x00019000)
    end += 32

    check = sum(out[0x38:end]) % 256
    struct.pack_into("<2IBI", out, 0x3165C, 0x2000, 1, check, 0xFFFFFFFF)
    return bytes(out)


# La Vita se congela al cargar si el texto del slot no sigue el formato en ingles
# (probado con un save de PC en espanol: etiquetas "Fecha:/Nombre:/..." cuelgan el juego).
LABELS = ("Date", "Name", "Difficulty", "Location", "Play Time", "Times Cleared")
TRANSLATE = {
    "Después\u3000de\u3000clase": "After\u3000class",
    "Instituto Yasogami": "Yasogami High",
    "Calle comercial": "Central Shopping District",
}


def _ascii_fold(text: str) -> str:
    """Quita tildes de las letras latinas; deja intactos fullwidth/espacio ideografico."""
    return "".join(
        unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode() if 0x80 <= ord(c) < 0x2000 else c
        for c in text)


def _fix(text: str) -> str:
    text = TRANSLATE.get(text, text)
    return _ascii_fold(text)


def _localize_block2(block: bytes) -> bytes:
    """Reescribe el bloque de texto de un slot con etiquetas en ingles."""
    lines = block.rstrip(b"\0").decode("utf-8", "replace").split("\n")
    vals = [ln.split(":", 1)[1] if ":" in ln else ln for ln in lines[:6]]
    if len(vals) < 6:
        return block
    when, tod = vals[0].split(":", 1) if ":" in vals[0] else (vals[0], "")
    vals[0] = when + (":" + _fix(tod) if tod else "")
    vals[1] = vals[1].replace(" Nv.:", " Lv:")
    vals[3] = _fix(vals[3])
    out = "".join(f"{lab}:{v}\n" for lab, v in zip(LABELS, vals))
    extra = [ln for ln in lines[6:] if ln]  # p.ej. "Marie Ending Cleared" en New Game+
    out += "\n".join(extra)
    return out.encode("utf-8")[:0xC4]


def convert_slot(binslot: bytes) -> bytes:
    body = binslot[BINSLOT_HEADER:]
    first = body[:0xC4]
    # Vita no usa la linea "LANGn" (n = idioma del save de PC)
    second = re.sub(rb"\nLANG\d+(?=\n)", b"", body[0xC4:0x188])
    second = _localize_block2(second)
    # la fecha/lugar del bloque 1 (0x44) y el texto de 0x44.. tambien se normalizan
    head = bytearray(first)
    place = bytes(head[0x44:0xC4]).rstrip(b"\0").decode("utf-8", "replace")
    if place and ":" in place:
        md, rest = place.split(":", 1)
        tod, _, loc = rest.partition(":")
        place = f"{md}:{_fix(tod)}:{_fix(loc)}"
        head[0x44:0xC4] = place.encode("utf-8")[:0x80].ljust(0x80, b"\0")
    second = second.ljust(0xC4, b"\0")[:0xC4]
    rest = body[0x188:0x34C]
    return (bytes(head).ljust(0xC4, b"\0") + second + rest).ljust(SLOT_SIZE, b"\0")


def build_sdslot(slots: dict, base=None) -> bytes:
    sd = bytearray(base) if base else bytearray(0x40400)
    if not base:
        sd[0:4] = b"SDSL"
        sd[9] = 1
    for i, data in slots.items():
        off = SLOT_SIZE + i * SLOT_SIZE
        sd[off:off + SLOT_SIZE] = data
        sd[0x200 + i] = 1
    return bytes(sd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_dir", type=Path, help="carpeta con los saves de PC (data00XX.bin + .binslot)")
    ap.add_argument("--base-sdslot", type=Path, help="sdslot.dat actual de tu Vita, para conservar los otros slots")
    ap.add_argument("--custom-diff", choices=("disable", "enable", "keep"), default="disable",
                    help="flag de dificultad custom (def. disable: la Vita no tiene ese menu)")
    ap.add_argument("-o", "--output", type=Path, help="carpeta de salida (por defecto <save_dir>_conv)")
    args = ap.parse_args()

    src = args.save_dir
    if not src.is_dir():
        ap.error(f"{src} no es una carpeta")
    if (src / "sce_sys/sdslot.dat").is_file():
        ap.error("esa carpeta ya contiene saves de Vita")
    dst = args.output or src.with_name(src.name + "_conv")
    (dst / "sce_sys").mkdir(parents=True, exist_ok=True)

    slots = {}
    names = [("system.bin", 0)] + [(f"data{i:04d}.bin", i) for i in range(1, NUM_SLOTS)]
    for fname, idx in names:
        binp, slotp = src / fname, src / f"{fname}slot"
        if not binp.exists():
            continue
        if not slotp.exists():
            print(f"  sin .binslot, se omite: {fname}")
            continue
        if idx == 0:
            shutil.copy(binp, dst / fname)
        else:
            (dst / fname).write_bytes(convert_bin(binp.read_bytes(), args.custom_diff))
        slots[idx] = convert_slot(slotp.read_bytes())
        print(f"  convertido {fname}")

    if not slots:
        ap.error("no se encontro ningun save con su .binslot")
    base = args.base_sdslot.read_bytes() if args.base_sdslot else None
    (dst / "sce_sys/sdslot.dat").write_bytes(build_sdslot(slots, base))
    print(f"Listo: {dst}")
    print("En VitaShell: copia el contenido de esa carpeta, abre ux0:user/00/savedata/<ID del juego> con "
          "'Open decrypted' (triangulo) y pegalo ahi. Copiar por FTP no funciona (el save esta cifrado).")


if __name__ == "__main__":
    main()
