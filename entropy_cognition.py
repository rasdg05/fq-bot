# -*- coding: utf-8 -*-
"""
================================================================================
  ENTROPY COGNITION v2 PATCH - FQ v4.1.1 Refactor
  
  PARCHE AL FINAL de entropy_cognition.py existente.
  NO reemplaza nada — solo agrega:
    - Columnas nuevas en signals (NULL-tolerantes, migracion suave)
    - count_closed_v2_buckets()
    - log_signal_v2() con FieldState completo
    - close_signal_v2() inyecta outcome al bucket memory loop
================================================================================

  INSTRUCCIONES: Pegar ESTE bloque al FINAL de entropy_cognition.py
  Las funciones legacy quedan vivas para compatibilidad con buckets viejos.
"""
# ============================================================
# PEGAR DESDE AQUI HASTA EL FINAL EN entropy_cognition.py
# ============================================================

# ============================================================
# SCHEMA v2 - columnas extra para FieldState
# ============================================================
SCHEMA_V2_MIGRATION = """
-- Columnas v4.1.1 (todas NULL-tolerantes para migracion suave)
ALTER TABLE signals ADD COLUMN killzone        TEXT;
ALTER TABLE signals ADD COLUMN killzone_priority TEXT;
ALTER TABLE signals ADD COLUMN pd_zone         TEXT;
ALTER TABLE signals ADD COLUMN pd_pct          REAL;
ALTER TABLE signals ADD COLUMN pd_hierarchy    TEXT;
ALTER TABLE signals ADD COLUMN confluence_count INTEGER;
ALTER TABLE signals ADD COLUMN confluence_list TEXT;
ALTER TABLE signals ADD COLUMN bias_4h         TEXT;
ALTER TABLE signals ADD COLUMN bias_1h         TEXT;
ALTER TABLE signals ADD COLUMN bias_aligned    INTEGER;
ALTER TABLE signals ADD COLUMN had_sweep       INTEGER;
ALTER TABLE signals ADD COLUMN crt_confirmed   INTEGER;
ALTER TABLE signals ADD COLUMN bucket_key_v2   TEXT;
ALTER TABLE signals ADD COLUMN alpha_hybrid    REAL;
ALTER TABLE signals ADD COLUMN w_killzone      REAL;
ALTER TABLE signals ADD COLUMN field_snapshot  TEXT;

CREATE INDEX IF NOT EXISTS idx_bucket_v2 ON signals(bucket_key_v2);
CREATE INDEX IF NOT EXISTS idx_killzone  ON signals(killzone);
"""

def migrate_schema_v2():
    """Aplica migracion v2 ignorando columnas que ya existen.
       Idempotente — safe correr varias veces."""
    with _lock:
        conn = _connect()
        try:
            for stmt in SCHEMA_V2_MIGRATION.strip().split(";"):
                s = stmt.strip()
                if not s:
                    continue
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as e:
                    # "duplicate column name" cuando ya migrado
                    if "duplicate column" not in str(e).lower():
                        log.warning("schema_v2 migration: {}".format(e))
            conn.commit()
            log.info("Schema v2 migrado/verificado")
        finally:
            conn.close()

# ============================================================
# CONTADORES v2
# ============================================================
def count_closed_v2_buckets():
    """Total de senales cerradas que tienen bucket_key_v2 (usado para alpha decay)"""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM signals "
                "WHERE bucket_key_v2 IS NOT NULL AND outcome IS NOT NULL"
            ).fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

def get_bucket_stats_v2(bucket_key_v2):
    """Como get_bucket_stats pero usando bucket_key_v2"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r FROM signals "
                "WHERE bucket_key_v2 = ? AND outcome IS NOT NULL",
                (bucket_key_v2,)
            ).fetchall()
        finally:
            conn.close()
    n = len(rows)
    if n < KAPPA_EVO_MIN_SAMPLES:
        return None
    wins = sum(1 for r in rows if r["outcome"] in ("tp1","tp2","tp3","tp4"))
    pnls = [r["pnl_r"] for r in rows if r["pnl_r"] is not None]
    win_rate = wins / n
    expectancy = sum(pnls) / len(pnls) if pnls else 0.0
    return {"n": n, "win_rate": win_rate, "expectancy": expectancy}

# ============================================================
# LOG SIGNAL V2 - registra con FieldState completo
# ============================================================
def log_signal_v2(signal_data, field_state):
    """
    Logea senal con FieldState completo.
    signal_data: igual estructura que log_signal legacy
    field_state: objeto FieldState de ict_smc
    """
    import json as _json
    try:
        # Serializar field para snapshot
        field_dict = field_state.to_dict() if hasattr(field_state, "to_dict") else {}
        field_json = _json.dumps(field_dict, default=str)[:50000]

        # bucket_key viejo + bucket_key_v2 nuevo coexisten
        bucket_key_legacy = signal_data.get("bucket_key", make_bucket_key(
            signal_data["session"],
            tier_from_pmaster(signal_data["p_master_raw"]),
            signal_data["direction"],
            curvature_sign(signal_data.get("support_weight", 0),
                          signal_data.get("resistance_weight", 0))
        ))
        bucket_key_v2 = field_state.bucket_key_v2(
            tier_from_pmaster(signal_data["p_master_raw"]),
            signal_data["direction"]
        )

        with _lock:
            conn = _connect()
            try:
                cur = conn.execute("""
                    INSERT INTO signals (
                        ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4,
                        p_master_raw, p_master_final, kappa_evo, session, w_clock,
                        tier, pspace_count, curvature_bal, macro_btc, macro_eth,
                        rsi6, rsi12, rsi24, h_lap_active, bucket_key, snapshot_json,
                        killzone, killzone_priority, pd_zone, pd_pct, pd_hierarchy,
                        confluence_count, confluence_list, bias_4h, bias_1h,
                        bias_aligned, had_sweep, crt_confirmed, bucket_key_v2,
                        alpha_hybrid, w_killzone, field_snapshot
                    ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,
                              ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    signal_data["direction"], signal_data["entry"], signal_data["sl"],
                    signal_data["tp1"], signal_data["tp2"], signal_data["tp3"], signal_data["tp4"],
                    signal_data["p_master_raw"], signal_data["p_master_final"],
                    signal_data["kappa_evo"], signal_data["session"],
                    signal_data["w_clock"], tier_from_pmaster(signal_data["p_master_raw"]),
                    signal_data.get("pspace_count", 0),
                    signal_data.get("support_weight", 0) - signal_data.get("resistance_weight", 0),
                    signal_data.get("macro_btc", 0), signal_data.get("macro_eth", 0),
                    signal_data.get("rsi6", 0), signal_data.get("rsi12", 0),
                    signal_data.get("rsi24", 0), signal_data.get("h_lap_active", 0),
                    bucket_key_legacy, _json.dumps(signal_data.get("snapshot", {}))[:10000],
                    # columnas v2
                    field_state.killzone, field_state.killzone_priority,
                    field_state.pd_zone, field_state.pd_pct, field_state.pd_hierarchy,
                    field_state.confluence_count,
                    ",".join(field_state.confluence_list)[:500],
                    field_state.bias_4h, field_state.bias_1h,
                    1 if field_state.bias_aligned else 0,
                    1 if field_state.recent_sweep else 0,
                    1 if (field_state.crt and field_state.crt.confirmed) else 0,
                    bucket_key_v2, signal_data.get("alpha_hybrid", 1.0),
                    field_state.w_killzone, field_json,
                ))
                sid = cur.lastrowid
                conn.commit()
                log.info("log_signal_v2 #{} bucket_v2={}".format(sid, bucket_key_v2))
                return sid
            finally:
                conn.close()
    except Exception as e:
        log.error("log_signal_v2: {}".format(e))
        return None
