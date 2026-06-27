# -*- coding: utf-8 -*-
"""
migrate_ledgers_to_sqlite — importa los motor_paper_*.jsonl existentes al SQLite
multi-símbolo (fq_motor.db), preservando la cadena SHA-256.

Cómo preserva la cadena: re-aplica los PAYLOADS en orden vía SqliteHashLedger.append,
que recomputa el hash desde genesis. Como los payloads y el orden son idénticos, la
cadena resultante es IDÉNTICA a la del JSONL (mismo prev/hash por fila). Idempotente:
si el símbolo ya tiene N filas en SQLite, solo agrega la cola que falta.

NO toca los JSONL (quedan como respaldo). Tras migrar + verificar, se prende
FQ_LEDGER_SQLITE=1 en Railway y el bot escribe en el SQLite de ahí en adelante.

Uso:
  python tools/migrate_ledgers_to_sqlite.py [--data-dir /data] [--db /data/fq_motor.db] [--dry-run]
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import execution as ex  # noqa: E402


def migrate(data_dir, db_path, dry_run=False):
    jsonls = sorted(glob.glob(os.path.join(data_dir, "motor_paper_*.jsonl")))
    if not jsonls:
        print("sin motor_paper_*.jsonl en %s" % data_dir)
        return 0
    total = 0
    for jp in jsonls:
        sym = ex._symbol_from_jsonl(jp)
        src = ex.DurableHashLedger.load(jp)               # verifica la cadena del JSONL
        n_src = len(src.records)
        if dry_run:
            print("[dry] %-12s %-40s -> %d filas" % (sym, os.path.basename(jp), n_src))
            continue
        dst = ex.SqliteHashLedger.load(db_path, sym)
        n_have = len(dst.records)
        for rec in src.records[n_have:]:                  # solo la cola que falta (idempotente)
            dst.append(rec["payload"])
        ok = dst.verify()
        # paridad de cadena: el head-hash del SQLite debe igualar al del JSONL
        same_head = (not n_src) or (dst.records[n_src - 1]["hash"] == src.records[n_src - 1]["hash"])
        print("%-12s %-40s  JSONL=%d  SQLite=%d  +%d  verify=%s  cadena=%s" % (
            sym, os.path.basename(jp), n_src, len(dst.records), len(dst.records) - n_have,
            "✓" if ok else "✗", "OK" if same_head else "DIFIERE"))
        if not (ok and same_head):
            print("  !! ABORTA: %s no migró íntegro — revisa antes de prender FQ_LEDGER_SQLITE" % sym)
            return 1
        total += len(dst.records)
    if not dry_run:
        print("\nMigración OK: %d filas en %s. Verifica y luego prende FQ_LEDGER_SQLITE=1." % (total, db_path))
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Migra los ledgers JSONL del motor a SQLite multi-símbolo.")
    default_dir = "/data" if os.path.isdir("/data") else "data"
    p.add_argument("--data-dir", default=default_dir)
    p.add_argument("--db", default=None, help="default <data-dir>/fq_motor.db")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    db = a.db or os.path.join(a.data_dir, "fq_motor.db")
    return migrate(a.data_dir, db, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
