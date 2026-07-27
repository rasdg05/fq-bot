#!/usr/bin/env node
/**
 * Instala la tarea diaria en tu máquina, sin CI de por medio.
 *
 * macOS usa launchd (sobrevive reinicios y recupera la corrida si la máquina
 * estaba apagada). Linux usa crontab. En los dos casos queda un solo trabajo,
 * reinstalable, y se puede quitar con `--uninstall`.
 *
 *   npm run cron:install
 *   npm run cron:install -- --uninstall
 *   npm run cron:install -- --hora 21
 */
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdirSync, existsSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir, platform } from "node:os";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const LABEL = "com.marea.superficie-iv";
const args = process.argv.slice(2);
const uninstall = args.includes("--uninstall");
const horaArg = args.indexOf("--hora");
const HORA = horaArg >= 0 ? Number(args[horaArg + 1]) : 20;
const MINUTO = 5;

if (!Number.isInteger(HORA) || HORA < 0 || HORA > 23) {
  console.error("La hora tiene que ser un entero de 0 a 23.");
  process.exit(1);
}

const node = process.execPath;
const script = join(ROOT, "scripts", "daily.mjs");

function macos() {
  const dir = join(homedir(), "Library", "LaunchAgents");
  const plist = join(dir, `${LABEL}.plist`);

  if (uninstall) {
    try {
      execFileSync("launchctl", ["bootout", `gui/${process.getuid?.()}/${LABEL}`], {
        stdio: "ignore",
      });
    } catch {
      /* si no estaba cargado, no pasa nada */
    }
    if (existsSync(plist)) unlinkSync(plist);
    console.log(`Quitada la tarea ${LABEL}.`);
    return;
  }

  mkdirSync(dir, { recursive: true });
  writeFileSync(
    plist,
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${node}</string>
    <string>${script}</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>${HORA}</integer>
    <key>Minute</key><integer>${MINUTO}</integer>
  </dict>
  <!-- si la máquina estaba apagada a esa hora, corre en cuanto despierta -->
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>${join(ROOT, "data", "iv", "cron.out.log")}</string>
  <key>StandardErrorPath</key><string>${join(ROOT, "data", "iv", "cron.err.log")}</string>
</dict>
</plist>
`,
  );

  try {
    execFileSync("launchctl", ["bootout", `gui/${process.getuid?.()}/${LABEL}`], {
      stdio: "ignore",
    });
  } catch {
    /* primera instalación */
  }
  execFileSync("launchctl", ["bootstrap", `gui/${process.getuid?.()}`, plist], {
    stdio: "inherit",
  });
  console.log(`Instalada: corre todos los días a las ${HORA}:${String(MINUTO).padStart(2, "0")}.`);
  console.log(`  plist: ${plist}`);
}

function linux() {
  const line = `${MINUTO} ${HORA} * * * cd ${ROOT} && ${node} ${script} >> ${join(ROOT, "data", "iv", "cron.out.log")} 2>&1 # ${LABEL}`;

  let actual = "";
  try {
    actual = execFileSync("crontab", ["-l"], { encoding: "utf8" });
  } catch {
    /* sin crontab previo */
  }
  // se quita cualquier versión anterior antes de poner la nueva
  const limpio = actual
    .split("\n")
    .filter((l) => l.trim() && !l.includes(LABEL))
    .join("\n");

  const nuevo = uninstall ? `${limpio}\n` : `${limpio}${limpio ? "\n" : ""}${line}\n`;
  execFileSync("crontab", ["-"], { input: nuevo });

  console.log(
    uninstall
      ? `Quitada la tarea ${LABEL}.`
      : `Instalada: corre todos los días a las ${HORA}:${String(MINUTO).padStart(2, "0")}.`,
  );
}

mkdirSync(join(ROOT, "data", "iv"), { recursive: true });

if (platform() === "darwin") macos();
else if (platform() === "linux") linux();
else {
  console.error(
    `No sé instalar tareas en ${platform()}. Corre a mano \`npm run daily\`, ` +
      `o programa este comando:\n  ${node} ${script}`,
  );
  process.exit(1);
}
