"""Prepare an incremental source patch for the original 5EHub Workshop package."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "build/5ehub-clean-baseline"
SOURCE = LAB / "source/5e_aimhub.original.js"
TEMPLATE = ROOT / "data/reference/ak47-template.json"
MEASURED = ROOT / "src/core/ak47.ts"
OUTPUT = LAB / "source/5e_aimhub.workshop-patched.js"
REPORT = LAB / "source/workshop-source-patch.json"


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Expected exactly one source anchor ({count}): {old[:100]!r}")
    return source.replace(old, new, 1)


def fit2(points: list[tuple[float, float]], values: list[float]) -> tuple[float, float]:
    xx = sum(x * x for x, _ in points)
    xy = sum(x * y for x, y in points)
    yy = sum(y * y for _, y in points)
    xv = sum(x * value for (x, _), value in zip(points, values))
    yv = sum(y * value for (_, y), value in zip(points, values))
    det = xx * yy - xy * xy
    if abs(det) < 1e-12:
        raise ValueError("RecoilMaster template is degenerate")
    return ((xv * yy - yv * xy) / det, (yv * xx - xv * xy) / det)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8-sig")
    template_doc = json.loads(TEMPLATE.read_text(encoding="utf-8-sig"))
    template = [tuple(map(float, point["templateOrigin"])) for point in template_doc["points"]]
    if len(template) != 30 or [p["shot"] for p in template_doc["points"]] != list(range(1, 31)):
        raise ValueError("Expected the original 30 ordered RecoilMaster AK points")

    measured_text = MEASURED.read_text(encoding="utf-8-sig")
    measured_block = measured_text.split("export const ak47:Recoil[]=[", 1)[1].split("];", 1)[0]
    measured = [(float(p), float(y)) for p, y in re.findall(
        r'"pitch":\s*([-0-9.eE]+),\s*"yaw":\s*([-0-9.eE]+)', measured_block
    )]
    if len(measured) != 30:
        raise ValueError(f"Expected 30 measured AK recoil samples, found {len(measured)}")

    relative_template = [(p[1] - template[0][1], p[2] - template[0][2]) for p in template]
    relative_pitch = [p - measured[0][0] for p, _ in measured]
    relative_yaw = [y - measured[0][1] for _, y in measured]
    pitch_y, pitch_z = fit2(relative_template, relative_pitch)
    yaw_y, yaw_z = fit2(relative_template, relative_yaw)
    pitch_rms = (sum((pitch_y * y + pitch_z * z - value) ** 2
                     for (y, z), value in zip(relative_template, relative_pitch)) / 30) ** 0.5
    yaw_rms = (sum((yaw_y * y + yaw_z * z - value) ** 2
                   for (y, z), value in zip(relative_template, relative_yaw)) / 30) ** 0.5
    template_js = json.dumps(template, separators=(",", ":"))
    fit_js = json.dumps({"pitchY": pitch_y, "pitchZ": pitch_z,
                         "yawY": yaw_y, "yawZ": yaw_z}, separators=(",", ":"))

    # The map's own CFG runs before the first useful round. These are the
    # original config arrays, edited in place so mode startup remains intact.
    source = replace_once(source, '    "mp_roundtime 60",', '    "mp_roundtime 9999",')
    source = replace_once(source, '    "mp_maxrounds 999",', '    "mp_maxrounds 0",')
    source = replace_once(source, '    "mp_roundtime_defuse 60",', '    "mp_roundtime_defuse 9999",')
    source = replace_once(source, '    "mp_ignore_round_win_conditions 1",',
                          '    "mp_ignore_round_win_conditions 1",\n'
                          '    "mp_timelimit 0",\n'
                          '    "sv_maxspeed 320",')

    # A mode switch can reapply its own settings. Re-enforce after its original
    # onEnter has had time to finish; no native callback is registered twice.
    source = replace_once(
        source,
        '        const templatePlatfrom = Instance.FindEntityByName("peek_template_platfrom");\n'
        '        templatePlatfrom.ForceSpawn({\n'
        '            x: templatePlatfrom.GetAbsOrigin().x,\n'
        '            y: templatePlatfrom.GetAbsOrigin().y,\n'
        '            z: randomPosition.z,\n'
        '        });',
        '        const templatePlatfrom = Instance.FindEntityByName("peek_template_platfrom");\n'
        '        // point_template.GetAbsOrigin() faults in the current native binding;\n'
        '        // these are the original Hammer coordinates of that exact template.\n'
        '        templatePlatfrom.ForceSpawn({ x: -1024, y: -512, z: randomPosition.z });',
    )
    source = replace_once(
        source,
        '        this.currentMode.onEnter();\n        // 触发事件',
        '        this.currentMode.onEnter();\n'
        '        if (SCRIPT_MAP_NOW === "5e_aimhub") {\n'
        '            Instance.Delay(0.5).then(() => __codexApplyPersistentTrainingSettings("mode-switch"))\n'
        '                .catch(error => printl("[CODEX-SESSION] mode-switch refresh failed=" + String(error)));\n'
        '        }\n'
        '        // 触发事件',
    )

    # Queue a narrow, one-shot input recovery after the original player manager
    # rebuilds its Player objects. It waits for a live pawn and yields to menus.
    source = replace_once(
        source,
        '            if (p)\n                p.applyGlow();\n        }\n    }\n'
        '    // ==================== 基础访问',
        '            if (p)\n                p.applyGlow();\n        }\n'
        '        __codexQueueHiddenUiRecovery(this);\n'
        '    }\n'
        '    // ==================== 基础访问',
    )
    source = replace_once(
        source,
        '    hide() {\n'
        '        if (!this._active)\n'
        '            return;\n'
        '        this._active = false;\n'
        '        Command("host_timescale 1"); // 关闭菜单恢复游戏时间\n'
        '        setInputCapture(this.player.id, false);',
        '    hide() {\n'
        '        const wasActive = this._active;\n'
        '        this._active = false;\n'
        '        if (!isFailActive())\n'
        '            setInputCapture(this.player.id, false);\n'
        '        if (!wasActive)\n'
        '            return;\n'
        '        __codexApplyBulletTime(); // Restore the selected training speed after closing the menu.',
    )

    # Preserve the map's one existing round-start and Think dispatchers.
    source = replace_once(
        source,
        '    safeTick("scheduleTick", () => tickCallback());',
        '    safeTick("CodexUnlimitedSession", () => __codexKeepTrainingSessionOpen());\n'
        '    safeTick("CodexHiddenUiRecovery", () => __codexRecoverHiddenUiCapture());\n'
        '    safeTick("scheduleTick", () => tickCallback());',
    )
    source = replace_once(
        source,
        '    PlayerMgr.initialize();\n'
        '    // initialize() 会重建所有 Player 对象，在此之后补充 UI 初始化',
        '    PlayerMgr.initialize();\n'
        '    __codexApplyPersistentTrainingSettings("post-config-round-start");\n'
        '    // initialize() 会重建所有 Player 对象，在此之后补充 UI 初始化',
    )

    source += r'''

// Workshop-local 5EHub AK guide. RecoilMaster's 30 original dots and material
// are copied byte-for-byte; this layer only renders a manual visual cue.
const __5ehubRmAkTemplate = __TEMPLATE__;
const __5ehubRmAkFit = __FIT__;
const __5ehubRmDotModel = "models/ulletical/recoil_master/patterns/dot_single_001.vmdl";
const __5ehubRmDotStyles = {
    path: { color: { r: 255, g: 0, b: 0, a: 255 }, scale: 0.65 },
    focus: { color: { r: 0, g: 255, b: 0, a: 255 }, scale: 1.0 },
    previous: { color: { r: 100, g: 100, b: 100, a: 255 }, scale: 0.50 },
    next: { color: { r: 200, g: 200, b: 200, a: 220 }, scale: 0.80 },
    hidden: { color: { r: 255, g: 0, b: 0, a: 0 }, scale: 0.65 },
};
let __5ehubRmMarkers = [];
let __5ehubRmMarkerStyles = [];
let __5ehubRmCreating;
let __5ehubRmRoundActive = false;
let __5ehubRmLoopGeneration = 0;
let __5ehubRmLoggedFirstRender = false;
let __5ehubRmGuideEnabled = true;
let __5ehubRmPart = "head";
let __5ehubRmShotCount = 0;
let __5ehubRmLastShotTime;
let __5ehubRmAmbiguous = false;
let __5ehubRmReloadUntil = 0;
let __5ehubRmHadHuman = false;

function __5ehubRmWrap(angle) {
    return ((angle + 180) % 360 + 360) % 360 - 180;
}
function __5ehubRmDot(a, b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}
function __5ehubRmLength(v) {
    return Math.hypot(v.x, v.y, v.z);
}
function __5ehubRmNormalize(v) {
    const n = __5ehubRmLength(v);
    return n > 1e-6 ? { x: v.x / n, y: v.y / n, z: v.z / n } : undefined;
}
function __5ehubRmAngles(v) {
    const toDegrees = 180 / Math.PI;
    return {
        pitch: Math.atan2(-v.z, Math.hypot(v.x, v.y)) * toDegrees,
        yaw: Math.atan2(v.y, v.x) * toDegrees,
        roll: 0,
    };
}
function __5ehubRmDirection(q) {
    const toRadians = Math.PI / 180;
    const pitch = q.pitch * toRadians;
    const yaw = q.yaw * toRadians;
    return { x: Math.cos(pitch) * Math.cos(yaw), y: Math.cos(pitch) * Math.sin(yaw), z: -Math.sin(pitch) };
}
function __5ehubRmResetShots() {
    __5ehubRmShotCount = 0;
    __5ehubRmLastShotTime = undefined;
    __5ehubRmAmbiguous = false;
    __5ehubRmReloadUntil = 0;
}
function __5ehubRmSetMarkerStyle(index, state) {
    const marker = __5ehubRmMarkers[index];
    if (!marker || !marker.IsValid() || __5ehubRmMarkerStyles[index] === state) return;
    const style = __5ehubRmDotStyles[state] ?? __5ehubRmDotStyles.path;
    marker.SetColor(style.color);
    marker.SetModelScale(style.scale);
    __5ehubRmMarkerStyles[index] = state;
}
function __5ehubRmHide() {
    for (let i = 0; i < __5ehubRmMarkers.length; i++) __5ehubRmSetMarkerStyle(i, "hidden");
}
async function __5ehubRmEnsureMarkers() {
    if (__5ehubRmCreating) return __5ehubRmCreating;
    __5ehubRmCreating = (async () => {
        const pending = [];
        for (let i = 0; i < 30; i++) {
            const name = "codex_5ehub_ak_dot_" + String(i + 1).padStart(2, "0");
            const marker = Instance.FindEntityByName(name);
            if (marker && marker.IsValid()) {
                __5ehubRmMarkers[i] = marker;
                continue;
            }
            pending.push([i, name]);
            Instance.ServerCommand('ent_create prop_dynamic { "targetname" "' + name +
                '" "model" "' + __5ehubRmDotModel +
                '" "solid" "0" "spawnflags" "256" "disableshadows" "1" "disablereceiveshadows" "1" }');
        }
        for (let attempt = 0; pending.length && attempt < 20; attempt++) {
            await Instance.Delay(0.1);
            for (let j = pending.length - 1; j >= 0; j--) {
                const [index, name] = pending[j];
                const marker = Instance.FindEntityByName(name);
                if (!marker || !marker.IsValid()) continue;
                __5ehubRmMarkers[index] = marker;
                pending.splice(j, 1);
            }
        }
        for (let i = 0; i < 30; i++) {
            const marker = __5ehubRmMarkers[i];
            if (!marker) {
                if (pending.some(([index]) => index === i))
                    Instance.Msg("[5E-AK] marker did not become available: codex_5ehub_ak_dot_" + String(i + 1).padStart(2, "0"));
                continue;
            }
            marker.SetModel(__5ehubRmDotModel);
            marker.SetModelScale(__5ehubRmDotStyles.hidden.scale);
            marker.SetColor(__5ehubRmDotStyles.hidden.color);
            __5ehubRmMarkerStyles[i] = "hidden";
        }
        Instance.Msg("[5E-AK] RecoilMaster markers=" +
            __5ehubRmMarkers.filter((marker) => marker && marker.IsValid()).length + "/30");
    })().catch((error) => Instance.Msg("[5E-AK] marker creation error=" + String(error))).finally(() => {
        __5ehubRmCreating = undefined;
    });
    return __5ehubRmCreating;
}
function __5ehubRmFindHuman() {
    for (const controller of Instance.GetAllPlayerControllers()) {
        if (!controller.IsConnected() || controller.IsBot()) continue;
        const pawn = controller.GetPlayerPawn();
        if (pawn && pawn.IsValid() && pawn.IsAlive()) return pawn;
    }
    return undefined;
}
function __5ehubRmAnchor(bot) {
    const eye = bot.GetEyePosition();
    const offset = __5ehubRmPart === "chest" ? -34 : __5ehubRmPart === "neck" ? -18 : -6;
    return { x: eye.x, y: eye.y, z: eye.z + offset };
}
function __5ehubRmCurrentIndex(now) {
    if (__5ehubRmLastShotTime !== undefined && now - __5ehubRmLastShotTime >= 2.5) {
        __5ehubRmResetShots();
        return 0;
    }
    if (now < __5ehubRmReloadUntil || __5ehubRmAmbiguous) return undefined;
    if (__5ehubRmLastShotTime !== undefined && now - __5ehubRmLastShotTime > 0.16) return undefined;
    if (__5ehubRmShotCount >= 30) return undefined;
    return Math.min(__5ehubRmShotCount, 29);
}
function __5ehubRmRender() {
    if (!__5ehubRmRoundActive || !__5ehubRmGuideEnabled || !peekMode.bPeekStatus) {
        __5ehubRmHide();
        return;
    }
    const human = __5ehubRmFindHuman();
    const bot = peekMode.victim;
    if (!human) {
        if (__5ehubRmHadHuman) __5ehubRmResetShots();
        __5ehubRmHadHuman = false;
        __5ehubRmHide();
        return;
    }
    __5ehubRmHadHuman = true;
    const weapon = human.GetActiveWeapon();
    const weaponName = weapon?.GetData()?.GetName()?.toLowerCase() ?? "";
    if (!bot || !bot.IsValid() || !bot.IsAlive() || !weaponName.includes("ak47")) {
        __5ehubRmHide();
        return;
    }
    const eye = human.GetEyePosition();
    const view = human.GetEyeAngles();
    const target = __5ehubRmAnchor(bot);
    const delta = { x: target.x - eye.x, y: target.y - eye.y, z: target.z - eye.z };
    const distance = __5ehubRmLength(delta);
    const baseRay = __5ehubRmNormalize(delta);
    if (!baseRay || distance < 32) {
        __5ehubRmHide();
        return;
    }
    const targetAngles = __5ehubRmAngles(delta);
    const basePitch = view.pitch + __5ehubRmWrap(targetAngles.pitch - view.pitch);
    const baseYaw = view.yaw + __5ehubRmWrap(targetAngles.yaw - view.yaw);
    const facing = __5ehubRmAngles({ x: -baseRay.x, y: -baseRay.y, z: -baseRay.z });
    const now = Instance.GetGameTime();
    const current = __5ehubRmCurrentIndex(now);
    if (current === undefined) {
        __5ehubRmHide();
        return;
    }
    for (let i = 0; i < 30; i++) {
        const marker = __5ehubRmMarkers[i];
        if (!marker || !marker.IsValid()) continue;
        const point = __5ehubRmAkTemplate[i];
        const dy = point[1] - __5ehubRmAkTemplate[0][1];
        const dz = point[2] - __5ehubRmAkTemplate[0][2];
        const recoilPitch = __5ehubRmAkFit.pitchY * dy + __5ehubRmAkFit.pitchZ * dz;
        const recoilYaw = __5ehubRmAkFit.yawY * dy + __5ehubRmAkFit.yawZ * dz;
        const ray = __5ehubRmDirection({ pitch: basePitch - recoilPitch, yaw: baseYaw - recoilYaw });
        const denominator = __5ehubRmDot(ray, baseRay);
        if (denominator <= 0.25) continue;
        const t = distance / denominator;
        marker.Move({
            position: { x: eye.x + ray.x * t, y: eye.y + ray.y * t, z: eye.z + ray.z * t },
            angles: facing,
        });
        const state = i < current ? "previous" : i === current ? "focus" : i === current + 1 ? "next" : "path";
        __5ehubRmSetMarkerStyle(i, state);
    }
    if (!__5ehubRmLoggedFirstRender) {
        __5ehubRmLoggedFirstRender = true;
        Instance.Msg("[5E-AK] render-ready anchor=" + __5ehubRmPart +
            " distance=" + Math.round(distance) + " shot=" + (current + 1) + "/30");
    }
}
function __5ehubRmLoop(generation) {
    if (generation !== __5ehubRmLoopGeneration) return;
    __5ehubRmRender();
    Instance.Delay(0.05).then(() => __5ehubRmLoop(generation)).catch((error) =>
        Instance.Msg("[5E-AK] render loop error=" + String(error)));
}
function __5ehubRmStartRound() {
    __5ehubRmResetShots();
    __5ehubRmRoundActive = true;
    __5ehubRmLoggedFirstRender = false;
    const generation = ++__5ehubRmLoopGeneration;
    __5ehubRmEnsureMarkers().then(() => __5ehubRmLoop(generation));
}
function __5ehubRmStopRound() {
    __5ehubRmRoundActive = false;
    __5ehubRmLoopGeneration++;
    __5ehubRmResetShots();
    __5ehubRmHide();
}
function __5ehubRmIsAk(weapon) {
    return weapon?.GetData()?.GetName()?.toLowerCase().includes("ak47") ?? false;
}
function __5ehubRmShowStatus(slot) {
    const text = "AK引导 " + (__5ehubRmGuideEnabled ? "开启" : "关闭") +
        " · 锚点 " + __5ehubRmPart + "（!akguide on/off，!akpart head/neck/chest）";
    showHintForSlot(slot, text);
}
function __5ehubRmSetGuide(enabled, slot) {
    __5ehubRmGuideEnabled = enabled;
    if (!enabled) __5ehubRmHide();
    if (slot !== undefined) __5ehubRmShowStatus(slot);
    Instance.Msg("[5E-AK] guide=" + (enabled ? "on" : "off") + " anchor=" + __5ehubRmPart);
}
function __5ehubRmSetPart(part, slot) {
    if (!["head", "neck", "chest"].includes(part)) return false;
    __5ehubRmPart = part;
    if (slot !== undefined) __5ehubRmShowStatus(slot);
    Instance.Msg("[5E-AK] anchor=" + part);
    return true;
}
function __5ehubRmConsoleCommand(name, callback) {
    try { Instance.RegisterCheatCommand(name, callback); }
    catch (_) { /* The engine may retain the command through a script reload. */ }
}
__5ehubRmConsoleCommand("akguide", (args) => {
    const value = args.trim().toLowerCase();
    __5ehubRmSetGuide(value === "on" ? true : value === "off" ? false : !__5ehubRmGuideEnabled, 0);
});
__5ehubRmConsoleCommand("akanchor", (args) => {
    __5ehubRmSetPart(args.trim().toLowerCase(), 0);
});

// Wrap existing PeekMode lifecycle methods; all native callbacks stay on the
// original EventBus and existing point_script input dispatcher.
const __5ehubOriginalPeekChoose = peekMode.peekChoose.bind(peekMode);
peekMode.peekChoose = function (...args) {
    __5ehubRmStopRound();
    const result = __5ehubOriginalPeekChoose(...args);
    if (this.bPeekStatus && this.victim && this.victim.IsValid()) __5ehubRmStartRound();
    return result;
};
const __5ehubOriginalPeekKill = peekMode.onPlayerKill.bind(peekMode);
peekMode.onPlayerKill = function (...args) {
    __5ehubRmStopRound();
    return __5ehubOriginalPeekKill(...args);
};
const __5ehubOriginalPeekExit = peekMode.onExit.bind(peekMode);
peekMode.onExit = function (...args) {
    __5ehubRmStopRound();
    return __5ehubOriginalPeekExit(...args);
};

// Reuse the existing OnGunFire -> GameEvents.GUN_FIRE dispatch for shot index.
eventBus.on(GameEvents.GUN_FIRE, (controller, weaponName) => {
    const user = PlayerMgr.resolveUser();
    if (!controller || controller.IsBot() || !user ||
        controller.GetPlayerSlot() !== user.id || !__5ehubRmRoundActive || !peekMode.bPeekStatus) return;
    if (!String(weaponName ?? "").toLowerCase().includes("ak47")) {
        __5ehubRmResetShots();
        return;
    }
    const now = Instance.GetGameTime();
    if (__5ehubRmLastShotTime === undefined || now - __5ehubRmLastShotTime >= 2.5) {
        __5ehubRmResetShots();
    } else if (now - __5ehubRmLastShotTime > 0.16) {
        __5ehubRmAmbiguous = true;
    }
    __5ehubRmShotCount++;
    __5ehubRmLastShotTime = now;
});
Instance.OnGunReload(({ weapon }) => {
    const owner = weapon.GetOwner();
    const controller = owner?.GetOriginalPlayerController();
    const user = PlayerMgr.resolveUser();
    if (!controller || controller.IsBot() || !user || controller.GetPlayerSlot() !== user.id || !__5ehubRmIsAk(weapon)) return;
    __5ehubRmResetShots();
    __5ehubRmReloadUntil = Instance.GetGameTime() + 2.4;
});
Instance.OnPlayerChat(({ player, text }) => {
    if (!player || player.IsBot()) return;
    const [command, value] = text.trim().toLowerCase().split(/\s+/);
    const slot = player.GetPlayerSlot();
    if (command === "!akguide" && (value === "on" || value === "off"))
        __5ehubRmSetGuide(value === "on", slot);
    else if (command === "!akpart")
        __5ehubRmSetPart(value, slot);
});

// Existing player-manager event handles bot death/reset; wrappers only add
// marker visibility and do not replace the original mode behavior.
const __codexTrainingClockState = { lastCheckGameTime: -1000 };
function __codexApplyPersistentTrainingSettings(reason) {
    for (const command of [
        "mp_timelimit 0", "mp_maxrounds 0", "mp_ignore_round_win_conditions 1",
        "mp_roundtime 9999", "mp_roundtime_defuse 9999", "mp_roundtime_hostage 9999",
        "sv_maxspeed 320",
    ]) Command(command);
    Instance.SetRoundRemainingTime(9999);
    printl("[CODEX-SESSION] persistent training settings applied: " + reason);
}
function __codexKeepTrainingSessionOpen() {
    const now = Instance.GetGameTime();
    if (now - __codexTrainingClockState.lastCheckGameTime < 2.0) return;
    __codexTrainingClockState.lastCheckGameTime = now;
    const remaining = Instance.GetRoundRemainingTime();
    if (!Number.isFinite(remaining) || remaining < 300) {
        Instance.SetRoundRemainingTime(9999);
        printl("[CODEX-SESSION] round timer refreshed from " + String(remaining) + "s to 9999s");
    }
}
const __codexHiddenUiRecovery = { pendingSlots: new Set(), lastCheckMs: 0 };
function __codexQueueHiddenUiRecovery(manager) {
    for (let slot = 0; slot <= 64; slot++) {
        const player = manager.get(slot);
        if (player && !player.getIsBot()) __codexHiddenUiRecovery.pendingSlots.add(slot);
    }
}
function __codexRecoverHiddenUiCapture() {
    if (__codexHiddenUiRecovery.pendingSlots.size === 0) return;
    const wallTime = Date.now();
    if (wallTime - __codexHiddenUiRecovery.lastCheckMs < 500) return;
    __codexHiddenUiRecovery.lastCheckMs = wallTime;
    for (const slot of Array.from(__codexHiddenUiRecovery.pendingSlots)) {
        const controller = Instance.GetPlayerController(slot);
        const player = PlayerMgr.get(slot);
        if (!controller || !player || controller.IsBot() || player.getIsBot()) {
            __codexHiddenUiRecovery.pendingSlots.delete(slot);
            continue;
        }
        const pawn = player.getPawn();
        if (!pawn || !pawn.IsValid() || !pawn.IsAlive()) continue;
        if (player.ui?.isActive() || isFailActive() || FlyCam._active || GrenadeCam.following) continue;
        setInputCapture(slot, false);
        player.setCameraEnabled(false);
        __codexHiddenUiRecovery.pendingSlots.delete(slot);
        printl("[CODEX-UI] released stale hidden-menu capture for live slot=" + slot);
    }
}
'''.replace("__TEMPLATE__", template_js).replace("__FIT__", fit_js)

    # Keep the original environment repairs, but replace the former fitted
    # rendering layer with the shared exact-table local validation layer.
    guide_start = source.index("// Workshop-local 5EHub AK guide.")
    settings_start = source.index("const __codexTrainingClockState", guide_start)
    new_guide = (ROOT / "src/diagnostics/5ehub-local-guide.js").read_text(encoding="utf-8")
    new_guide = new_guide.replace("__MEASURED__", json.dumps(
        [{"pitch": p, "yaw": y} for p, y in measured], separators=(",", ":")))
    profiles_path = ROOT / "data/calibration/weapon-profiles.json"
    profiles = json.loads(profiles_path.read_text(encoding="utf-8")) if profiles_path.exists() else {}
    profiles["weapon_ak47"] = {"label": "AK-47", "recoil": [{"pitch": p, "yaw": y} for p, y in measured]}
    new_guide = new_guide.replace("__WEAPON_PROFILES__", json.dumps(profiles, ensure_ascii=False, separators=(",", ":")))
    display_doc = json.loads((ROOT / "data/calibration/fixed-camera-display.json").read_text(encoding="utf-8"))
    display_profiles = display_doc["profiles"]
    if set(display_profiles) != set(profiles):
        raise ValueError("Fixed display calibration must cover every supported weapon profile")
    for name, points in display_profiles.items():
        if name not in profiles or len(points) != len(profiles[name]["recoil"]):
            raise ValueError("Incomplete fixed display calibration for " + name)
        if not all(math.isfinite(point[key]) for point in points for key in ("pitch", "yaw")):
            raise ValueError("Non-finite fixed display calibration for " + name)
    new_guide = new_guide.replace("__DISPLAY_CALIBRATION__", json.dumps(display_profiles, separators=(",", ":")))
    catalog_doc = json.loads((ROOT / "data/recoilmaster-weapons.json").read_text(encoding="utf-8"))
    catalog = [p for p in catalog_doc["profiles"] if p["key"] not in catalog_doc.get("excludedProfiles", [])]
    new_guide = new_guide.replace("__WEAPON_CATALOG__", json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    # Only the legacy screen diagnostic uses this size. Do not bake the
    # developer's Steam account video settings into a portable release.
    viewport = {"width": 1920, "height": 1080}
    new_guide = new_guide.replace("__VIEWPORT__", json.dumps(viewport))
    source = source[:guide_start] + new_guide + "\n" + source[settings_start:]
    source += "\n" + (ROOT / "src/diagnostics/5ehub-bullet-time.js").read_text(encoding="utf-8")
    source += "\n" + (ROOT / "src/diagnostics/5ehub-training-menu.js").read_text(encoding="utf-8")
    source += "\n" + (ROOT / "src/diagnostics/5ehub-weapon-calibration.js").read_text(encoding="utf-8")
    source = replace_once(source,
        '        const now = Instance.GetGameTime();\n        // 超时：1 秒内未再次按下 Tab，重置计数',
        '        const now = Date.now() / 1000;\n        // 双击 Tab 始终按真实时间判断，与子弹时间速度无关')
    source = replace_once(source,
        '    safeTick("AutoAim", () => AutoAim.tick());',
        '    safeTick("AutoAim", () => AutoAim.tick());\n'
        '    safeTick("CodexAKGuide", () => __5ehubRmRender());\n'
        '    Instance.QueueAfterThinks(() => safeTick("CodexCameraProbe", () => __5ehubCameraProbeTick()));')
    OUTPUT.write_text(source.rstrip() + "\n", encoding="utf-8")
    report = {
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "sourceSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "outputSha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "recoilMasterPointCount": len(template),
        "measuredAkSampleCount": len(measured),
        "weaponProfiles": {name: len(profile["recoil"]) for name, profile in profiles.items()},
        "fixedDisplayProfiles": {name: len(points) for name, points in display_profiles.items()},
        "fitCoefficients": {"pitchY": pitch_y, "pitchZ": pitch_z, "yawY": yaw_y, "yawZ": yaw_z},
        "fitRmsDegrees": {"pitch": pitch_rms, "yaw": yaw_rms},
        "activeRenderer": "native DebugSphere at target depth, duration zero, updated by original map Think; no hidden prop creation or movement",
        "defaultDisplay": "world",
        "drawingVersions": {
            "default": 2,
            "1": "all-weapons-2 original screen projection, glyphs, colors and raw compensation rays",
            "2": "current engine-projected world reference and live current-camera cue",
            "menu": "double Tab > aim and target > drawing version",
        },
        "activeCompensation": "independent measured tables selected by native weapon and scope state; legacy fit is not used",
        "localAutomaticAim": "disabled by default; akauto on explicitly enables it for local validation",
        "viewport": viewport,
        "originalStyles": {
            "path": {"color": [255, 0, 0, 255], "scale": 0.65},
            "focus": {"color": [0, 255, 0, 255], "scale": 1.0},
            "previous": {"color": [100, 100, 100, 255], "scale": 0.5},
            "next": {"color": [200, 200, 200, 220], "scale": 0.8},
        },
        "changes": [
            "5EHub original CONFIG, event routing, PeekMode spawn/reset, geometry, and mode buttons retained",
            "PeekMode template ForceSpawn uses the unchanged point_template Hammer x/y origin because GetAbsOrigin() on that native binding faults in the current build",
            "map time and round limits disabled; round remaining time renewed before expiry",
            "restore sv_maxspeed after original CFG and on mode changes",
            "one-shot hidden menu input-capture recovery after a live human pawn is ready; active menus and cameras are respected",
            "AK drawing and local automatic aim use the same measured table and current Bot position in the original map Think",
            "dynamic dots are created in a batch and looked up with bounded retries before the render loop starts",
            "shot state uses the existing EventBus gun-fire event; automatic aiming pauses during partial recoil recovery",
            "chat: !akguide on|off; !akpart head|neck|chest; console: akguide [on|off|toggle], akanchor <part>",
            "akauto on/off controls Workshop-local native SetEyeAngles; no external memory or mouse input tools",
        ],
        "limits": [
            "Head anchor traced to hitgroup 1 in the actual Workshop scene; neck/chest use fixed eye-relative offsets, not model-specific bones.",
            "Copied prop markers did not display for the user. Native DebugSphere rendering was confirmed visible; it is a development drawing API, so production Workshop distribution still needs validation.",
            "The API does not expose current aim punch; compensation uses full-spray measurement. Partial recovery and arbitrary recoil-scale changes are not exactly compensated.",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
