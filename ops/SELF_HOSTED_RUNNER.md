# Runner self-hosted para research pesado (cosecha F3, F4 BTC 48m, etc.)

GitHub-hosted runners se cortan a **6h**. El research denso a **step1** (cada
vela; ~311k para SOL 36m) necesita ~7-11h. Solución: un **VPS barato** como
**runner self-hosted** → el MISMO workflow `Research`, lanzado con un click,
corre en tu hardware **sin tope**. Capacidad reutilizable para toda cosecha/F4
futura.

`research.yml` ya está cableado: cuando lanzás con **`cosecha=true`**, el job
usa `runs-on: self-hosted` y `timeout-minutes: 1440` (24h). El resto de runs
(normal/poda/schedule) sigue en `ubuntu-latest` gratis.

---

## 1. El VPS (una vez)

Cualquiera sirve; recomendado **8 GB RAM** (el índice de retrieval sobre ~311k
estados consume memoria). Ubuntu 22.04/24.04 x64.

| Proveedor | Plan | RAM/vCPU | Precio aprox |
|---|---|---|---|
| **Hetzner** | CX32 | 8 GB / 4 vCPU | ~€6.5/mo (o por horas) |
| Hetzner | CX22 | 4 GB / 2 vCPU | ~€4/mo (justo, puede faltar RAM) |
| DigitalOcean | Basic 8GB | 8 GB / 2 vCPU | ~$48/mo (o droplet por horas) |
| AWS/GCP spot | c7i.large | 4 GB / 2 vCPU | ~$0.05-0.10/h |

Tip: en Hetzner podés crearlo, correr la cosecha (~8h ≈ €0.07) y borrarlo, o
dejarlo idle para F4/futuras (cuesta centavos/día).

## 2. Prerrequisitos en el VPS (como root, una vez)

```bash
sudo apt-get update
sudo apt-get install -y git curl tar libgomp1 build-essential
# (Python 3.12 NO hace falta instalarlo: actions/setup-python lo baja al runner)
# Crea un usuario no-root para el runner (buena práctica):
sudo useradd -m -s /bin/bash runner && sudo usermod -aG sudo runner
echo "runner ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/runner   # sudo sin password (para apt del workflow)
sudo su - runner
```

## 3. Registrar el runner (como usuario `runner`)

En GitHub: **repo `rasdg05/fq-bot` → Settings → Actions → Runners → New
self-hosted runner → Linux / X64**. Te muestra comandos con un **token**
(de un solo uso, caduca pronto). Cópialos tal cual — son de la forma:

```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-<VER>.tar.gz -L \
  https://github.com/actions/runner/releases/download/v<VER>/actions-runner-linux-x64-<VER>.tar.gz
tar xzf actions-runner-linux-x64-<VER>.tar.gz
./config.sh --url https://github.com/rasdg05/fq-bot --token <TOKEN_DE_LA_UI>
```
En `config.sh` aceptá los defaults (labels: `self-hosted` queda por defecto, que
es justo lo que el workflow espera).

## 4. Correrlo como servicio (sobrevive reinicios, corre en background)

```bash
sudo ./svc.sh install runner
sudo ./svc.sh start
sudo ./svc.sh status        # debe decir "active (running)"
```
En GitHub → Settings → Actions → Runners debe aparecer **Idle** (verde).

## 5. VERIFICAR el sharding (una vez, ~minutos) — paso de seguridad

La cosecha usa **sharding** (parte el replay por fecha en `nproc` procesos
paralelos → ~22h baja a ~2-3h). Antes de confiar en la cosecha grande,
comprobá que el sharding reproduce EXACTO el cubo sin shardear. En el VPS, como
usuario `runner`, con algo de data ya descargada (o bajá un rango chico):

```bash
cd ~/actions-runner/_work/fq-bot/fq-bot   # o donde clonó el runner; o git clone aparte
# baja ~4 meses de SOL para la prueba (rápido):
for TF in 5m 15m 1h; do python tools/build_dataset.py --symbol SOL/USDT \
    --timeframe $TF --market swap --years 0.4 --exchanges okx; done
python tools/cosecha_shard.py --symbol SOL/USDT --verify --verify-days 90
```
Debe imprimir **`✅ IDÉNTICOS`**. Si dice `❌ DIFIEREN`, avisame ANTES de la
cosecha grande (hay un bug de borde) — no la lances shardeada.

## 6. Lanzar la cosecha (sharded, ~2-3h)

Con el runner en **Idle** y el verify en ✅, avísame: pongo `cosecha` con default
`true` (truco del bug de GitHub mobile) → vos lanzás **Actions → Research → Run**
de un toque. El job corre en TU VPS, **shardeado en `nproc` procesos**, hace
**BTC ~84m + SOL ~72m a step1** (máxima data; `build_dataset` trunca a lo que OKX
tenga) y sube los cubos `research-report-BTC_USDT` / `_SOL_USDT` a GitHub. Yo los
bajo por MCP y corro **F3 `run_pooled --sweep`** sobre el cubo POOLED (~1.4-1.9k
eventos, sobre el gate de 1000).

> Paralelo de símbolos: con **1 runner** los 2 jobs (BTC, SOL) corren en serie
> (cada uno shardeado → ~3h c/u ≈ 6h). Para correrlos a la vez, registrá el
> runner DOS veces (pasos 3-4 en dos carpetas `actions-runner-1/-2`) → ~3h total.
> En CCX43 (16 núcleos) cada job shardea en ~8 → vuela.
> Si el job queda "Queued" = el runner no está online (`sudo ./svc.sh status`).

## 6. Después

- Dejá el runner idle para F4 (BTC 48m) y futuras cosechas — es la capacidad
  reutilizable que pediste. O `sudo ./svc.sh stop` + borrá el VPS si fue one-off.
- Para quitarlo: `sudo ./svc.sh uninstall && ./config.sh remove --token <TOKEN>`.

## Seguridad

Repo privado → solo admins del repo disparan workflows en el runner. Aun así,
no instales el runner en una máquina con secretos sensibles; un VPS dedicado y
desechable es lo ideal.
