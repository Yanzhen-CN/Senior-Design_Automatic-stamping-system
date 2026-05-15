const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const ui = {
  status: $("#runtimeStatus"),
  console: $("#consoleBox"),
  gcode: $("#gcodeBox"),
  stage: $("#stage"),
  motionMap: $("#motionMapCanvas"),
  clearConsoleBtn: $("#clearConsoleBtn"),
  offView: $("#cameraOffView"),
  video: $("#cameraVideo"),
  image: $("#stageImage"),
  overlay: $("#overlay"),
  detectDebugImage: $("#detectDebugImage"),
  detectDebugMeta: $("#detectDebugMeta"),
  workflowMode: $("#workflowMode"),
  modeA: $("#modeABlock"),
  modeB: $("#modeBBlock"),
  modeC: $("#modeCBlock"),
  documentFile: $("#documentFile"),
  modeCConfirmPreview: $("#modeCConfirmPreview"),
  modeCConfirmMeta: $("#modeCConfirmMeta"),
  modeCDebugPreview: $("#modeCDebugPreview"),
  modeCDebugMeta: $("#modeCDebugMeta"),
  cameraSimulationFile: $("#cameraSimulationFile"),
  cameraSimulationBtn: $("#cameraSimulationBtn"),
  cameraSimulationTopBtn: $("#cameraSimulationTopBtn"),
  cameraSimulationAdjust: $("#cameraSimulationAdjust"),
  cameraSimulationAdjustLabel: $("#cameraSimulationAdjustLabel"),
  rotateSimulationLeftBtn: $("#rotateSimulationLeftBtn"),
  rotateSimulationRightBtn: $("#rotateSimulationRightBtn"),
  confirmSimulationBtn: $("#confirmSimulationBtn"),
  cancelSimulationPreviewBtn: $("#cancelSimulationPreviewBtn"),
  motionConnectBtn: $("#motionConnectBtn"),
  cameraStatus: $("#cameraStatusText"),
  cameraSettings: $("#cameraSettings"),
  cameraSource: $("#cameraSourceSelect"),
  cameraDevice: $("#cameraDeviceSelect"),
  cameraDeviceField: $("#cameraDeviceField"),
  streamUrlField: $("#streamUrlField"),
  streamUrl: $("#streamUrlInput"),
  cameraWidth: $("#cameraWidthInput"),
  cameraHeight: $("#cameraHeightInput"),
  cameraDistance: $("#cameraDistanceInput"),
  crosshair: $("#cameraCrosshairInput"),
  activeCalPoint: $("#activeCalPoint"),
  calibrationTable: $("#calibrationTable"),
  activePaperRoiPoint: $("#activePaperRoiPoint"),
  paperRoiTable: $("#paperRoiTable"),
  activeStampRegionBoundPoint: $("#activeStampRegionBoundPoint"),
  stampRegionBoundTable: $("#stampRegionBoundTable"),
  targetActionButtons: $("#targetActionButtons"),
  jogStep: $("#jogStep"),
  serialPort: $("#serialPortSelect"),
  serialBaudrate: $("#serialBaudrateInput"),
  serialDryRun: $("#serialDryRunInput"),
  rollerLength: $("#rollerLengthInput"),
  axisXScale: $("#axisXScaleInput"),
  axisYScale: $("#axisYScaleInput"),
  axisZScale: $("#axisZScaleInput"),
  axisXMeasured: $("#axisXMeasuredInput"),
  axisYMeasured: $("#axisYMeasuredInput"),
  axisZMeasured: $("#axisZMeasuredInput"),
  motionCalStepReadout: $("#motionCalStepReadout"),
  flashPort: $("#flashPortSelect"),
  flashHex: $("#flashHexPathInput"),
  flashLog: $("#flashLogBox"),
};

const readout = {
  job: $("#jobReadout"),
  relative: $("#relativeReadout"),
  pixel: $("#pixelReadout"),
  paper: $("#paperReadout"),
  real: $("#realReadout"),
  command: $("#commandReadout"),
  clicked: $("#calClickedReadout"),
  serialConnection: $("#serialConnectionReadout"),
  serialPort: $("#serialPortReadout"),
  droMx: $("#droMx"),
  droMy: $("#droMy"),
  droMz: $("#droMz"),
  droWx: $("#droWx"),
  droWy: $("#droWy"),
  droWz: $("#droWz"),
  bounds: $("#boundsReadout"),
  motionConnState: $("#motionConnStateReadout"),
  motionConnPort: $("#motionConnPortReadout"),
};

let appConfig = null;
let cameraStream = null;
let cameraMode = "off";
let cameraSimulationActive = false;
let cameraSimulationPending = false;
let cameraModeBeforeSimulation = "off";
let imageSrcBeforeSimulation = "";
let pendingSimulationImageData = "";
let pendingSimulationName = "";
let selectedPixel = null;
let documentPixel = null;
let targetPixel = null;
let documentInfo = null;
let documentPreviewActive = false;
let cameraModeBeforeDocument = "off";
let imageSrcBeforeDocument = "";
let confirmedModeCRelative = null;
let confirmedModeCDocumentPixel = null;
let detectedPaper = null;
let detectedPaperVisibleUntil = 0;
let detectedPaperTimer = null;
let activeJob = null;
let serialPollTimer = null;
let serialPollBusy = false;
let serialBurstTimer = null;
let serialBurstRemaining = 0;
const activeHoldReleases = new Set();
let boundsCapture = { origin: null, xMax: null, yMax: null };
let runtimeBounds = null;
let lastWorkPosition = { x: null, y: null, z: null };
let draggingCalPointIndex = null;
let draggingCalPointerId = null;
let draggingStampRegionPointIndex = null;
let draggingStampRegionPointerId = null;
let draggingStampRegionEdgeIndex = null;
let draggingStampRegionEdgePointerId = null;
let draggingStampRegionLastPoint = null;
let movedWhileDraggingCal = false;
let movedWhileDraggingStampRegion = false;
let stampRegionDrawIndex = 0;
let suppressNextOverlayClick = false;
let showCalibrationOverlay = true;
let showStampRegionOverlay = true;
let cameraEditTarget = "region";
const paperRoiLabels = ["region_top_left", "region_top_right", "region_bottom_right", "region_bottom_left"];

function cameraTabActive() {
  return $("#cameraPanel")?.classList.contains("active");
}

function advancedTabActive() {
  return $("#advancedPanel")?.classList.contains("active");
}

function activeCameraEditPanel() {
  if (cameraEditTarget === "region") return cameraTabActive();
  if (cameraEditTarget === "calibration") return advancedTabActive();
  return false;
}

function cloneBoundsCaptured(captured) {
  return {
    origin: Array.isArray(captured?.origin) ? [...captured.origin] : null,
    xMax: Array.isArray(captured?.xMax) ? [...captured.xMax] : null,
    yMax: Array.isArray(captured?.yMax) ? [...captured.yMax] : null,
  };
}

function log(message, data = null) {
  const time = new Date().toLocaleTimeString();
  const extra = data ? `\n${JSON.stringify(data, null, 2)}` : "";
  ui.console.textContent = `[${time}] ${message}${extra}\n\n${ui.console.textContent}`;
}

function clearConsole() {
  ui.console.textContent = "";
  setStatus("Console cleared");
}

function setStatus(message) {
  ui.status.textContent = message;
}

function activateTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `${name}Panel`));
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const response = await fetch(path, { headers, ...options });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return response.json();
}

async function task(label, fn) {
  try {
    setStatus(label);
    const result = await fn();
    return result;
  } catch (error) {
    log(error.message);
    setStatus("Error");
    return null;
  }
}

function fmtPoint(point) {
  if (!Array.isArray(point)) return "-";
  return `${Number(point[0]).toFixed(3)}, ${Number(point[1]).toFixed(3)}`;
}

function fmtRelative(point) {
  if (!Array.isArray(point)) return "-";
  return `${Number(point[0]).toFixed(4)}, ${Number(point[1]).toFixed(4)}`;
}


function numOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function currentWorkXYZ() {
  return { ...lastWorkPosition };
}

function runtimeXYBoundsActive() {
  return Boolean(runtimeBounds?.enabled);
}

function workspaceBoundsEnabled() {
  return runtimeXYBoundsActive();
}

function setEnableBoundsButtonText() {
  const button = $("#applyBoundsBtn");
  if (!button) return;
  button.textContent = workspaceBoundsEnabled() ? "Disable" : "Enable";
}

function axisLimits(axis) {
  if (axis === "x" || axis === "y") {
    if (!workspaceBoundsEnabled()) {
      return { min: null, max: null };
    }
    const rt = runtimeBounds?.effective?.[axis];
    return {
      min: numOrNull(rt?.min),
      max: numOrNull(rt?.max),
    };
  }
  const cfgAxis = appConfig?.machine?.axes?.[axis];
  let min = numOrNull(cfgAxis?.min_commanded_mm);
  let max = numOrNull(cfgAxis?.max_commanded_mm);
  return { min, max };
}

function assertAxisInBounds(axis, current, target, context) {
  const { min, max } = axisLimits(axis);
  const eps = 1e-9;
  if (min !== null && current < min - eps) {
    if (target <= current + eps) {
      throw new Error(`${context} blocked: ${axis.toUpperCase()} is below min, move +${axis.toUpperCase()} to recover`);
    }
    return;
  }
  if (max !== null && current > max + eps) {
    if (target >= current - eps) {
      throw new Error(`${context} blocked: ${axis.toUpperCase()} is above max, move -${axis.toUpperCase()} to recover`);
    }
    return;
  }
  if (min !== null && target < min - eps) {
    throw new Error(`${context} blocked: ${axis.toUpperCase()} target ${target.toFixed(3)} < min ${min.toFixed(3)}`);
  }
  if (max !== null && target > max + eps) {
    throw new Error(`${context} blocked: ${axis.toUpperCase()} target ${target.toFixed(3)} > max ${max.toFixed(3)}`);
  }
}

function assertRelativeMoveInBounds(dxCmd = 0, dyCmd = 0, dzCmd = 0, context = "Move") {
  const pos = currentWorkXYZ();
  if (pos.x !== null) assertAxisInBounds("x", pos.x, pos.x + dxCmd, context);
  if (pos.y !== null) assertAxisInBounds("y", pos.y, pos.y + dyCmd, context);
  if (pos.z !== null) assertAxisInBounds("z", pos.z, pos.z + dzCmd, context);
}

function assertAbsoluteMoveInBounds(targets, context = "Move") {
  const pos = currentWorkXYZ();
  if (targets.x !== undefined && targets.x !== null && pos.x !== null) {
    assertAxisInBounds("x", pos.x, Number(targets.x), context);
  }
  if (targets.y !== undefined && targets.y !== null && pos.y !== null) {
    assertAxisInBounds("y", pos.y, Number(targets.y), context);
  }
  if (targets.z !== undefined && targets.z !== null && pos.z !== null) {
    assertAxisInBounds("z", pos.z, Number(targets.z), context);
  }
}

function realDeltaToCommanded(axis, realDeltaMm) {
  const cfgAxis = appConfig?.machine?.axes?.[axis];
  if (!cfgAxis) return realDeltaMm;
  const ratio = axisEffectiveMmPerCommanded(axis);
  if (!Number.isFinite(ratio) || Math.abs(ratio) < 1e-9) {
    throw new Error(`Axis ${axis.toUpperCase()} calibration ratio is invalid`);
  }
  const sign = cfgAxis.invert ? -1.0 : 1.0;
  return sign * Number(realDeltaMm) / ratio;
}

function commandedDeltaToReal(axis, commandedDelta) {
  const cfgAxis = appConfig?.machine?.axes?.[axis];
  if (!cfgAxis) return Number(commandedDelta);
  const ratio = axisEffectiveMmPerCommanded(axis);
  if (!Number.isFinite(ratio) || Math.abs(ratio) < 1e-9) {
    return Number(commandedDelta);
  }
  const sign = cfgAxis.invert ? -1.0 : 1.0;
  return sign * Number(commandedDelta) * ratio;
}

function axisTheoreticalStepsPerMm(cfgAxis) {
  const motorSteps = Number(cfgAxis?.motor_steps_per_rev);
  const microsteps = Number(cfgAxis?.microsteps);
  const pulleyTeeth = Number(cfgAxis?.pulley_teeth);
  const beltPitch = Number(cfgAxis?.belt_pitch_mm);
  if (
    !Number.isFinite(motorSteps) || !Number.isFinite(microsteps)
    || !Number.isFinite(pulleyTeeth) || !Number.isFinite(beltPitch)
  ) {
    return null;
  }
  const travelPerRev = pulleyTeeth * beltPitch;
  if (Math.abs(travelPerRev) < 1e-9) return null;
  return (motorSteps * microsteps) / travelPerRev;
}

function axisEffectiveMmPerCommanded(axis) {
  const cfgAxis = appConfig?.machine?.axes?.[axis];
  if (!cfgAxis) return 1;
  const base = Number(cfgAxis.actual_mm_per_commanded_mm);
  if (!Number.isFinite(base) || Math.abs(base) < 1e-9) return base;
  const theory = axisTheoreticalStepsPerMm(cfgAxis);
  const configuredSteps = Number(cfgAxis.steps_per_mm);
  if (!Number.isFinite(theory) || Math.abs(theory) < 1e-9) return base;
  const useSteps = Number.isFinite(configuredSteps) && configuredSteps > 1e-9 ? configuredSteps : theory;
  return base * (useSteps / theory);
}

function refreshMotionCalibrationReadout() {
  if (!ui.motionCalStepReadout) return;
  const jogStep = Number(ui.jogStep?.value);
  if (!Number.isFinite(jogStep) || jogStep <= 0) {
    ui.motionCalStepReadout.textContent = "-";
    return;
  }
  const rx = axisEffectiveMmPerCommanded("x");
  const ry = axisEffectiveMmPerCommanded("y");
  const rz = axisEffectiveMmPerCommanded("z");
  ui.motionCalStepReadout.textContent = `one jog click target: ${jogStep.toFixed(3)} mm (X ratio ${rx.toFixed(4)}, Y ${ry.toFixed(4)}, Z ${rz.toFixed(4)})`;
}

function commandedRangeToReal(axis, range) {
  const minCmd = numOrNull(range?.min);
  const maxCmd = numOrNull(range?.max);
  if (minCmd === null || maxCmd === null) {
    return { min: null, max: null };
  }
  const a = commandedDeltaToReal(axis, minCmd);
  const b = commandedDeltaToReal(axis, maxCmd);
  return { min: Math.min(a, b), max: Math.max(a, b) };
}

function updateStageMode(mode) {
  cameraMode = mode;
  ui.offView.classList.toggle("hidden", mode !== "off");
  ui.video.classList.toggle("hidden", mode !== "local-video" && mode !== "stream-video");
  ui.image.classList.toggle(
    "hidden",
    mode !== "document"
      && mode !== "stream-image"
      && mode !== "simulation-image"
      && mode !== "simulation-pending",
  );
  syncOverlaySize();
  drawOverlay();
}

function cameraFrameReady() {
  return (
    cameraMode === "local-video"
    || cameraMode === "stream-video"
    || cameraMode === "stream-image"
    || cameraMode === "simulation-image"
  );
}

function liveCameraFrameReady() {
  return (
    cameraMode === "local-video"
    || cameraMode === "stream-video"
    || cameraMode === "stream-image"
  );
}

function setCameraButtons(active, label = "Camera Off") {
  $("#cameraToggleBtn").textContent = active ? "Off" : "On";
  $("#cameraToggleTopBtn").textContent = active ? label : "Camera On";
}

function setSimulationButtons(active) {
  cameraSimulationActive = Boolean(active);
  ui.cameraSimulationAdjust?.classList.toggle("hidden", !cameraSimulationPending);
  const text = active ? "Cancel Simulation" : "Camera Simulation";
  const compactText = active ? "Cancel Simulation" : "Simulation";
  if (ui.cameraSimulationTopBtn) ui.cameraSimulationTopBtn.textContent = text;
  if (ui.cameraSimulationBtn) ui.cameraSimulationBtn.textContent = compactText;
  ui.cameraSimulationTopBtn?.classList.toggle("danger", Boolean(active));
  ui.cameraSimulationTopBtn?.classList.toggle("secondary", !active);
  ui.cameraSimulationBtn?.classList.toggle("danger", Boolean(active));
  ui.cameraSimulationBtn?.classList.toggle("secondary", !active);
}

function activeMediaSize() {
  if (!ui.video.classList.contains("hidden") && ui.video.videoWidth) {
    return [ui.video.videoWidth, ui.video.videoHeight];
  }
  if (!ui.image.classList.contains("hidden") && ui.image.naturalWidth) {
    return [ui.image.naturalWidth, ui.image.naturalHeight];
  }
  const rect = ui.stage.getBoundingClientRect();
  return [Math.round(rect.width), Math.round(rect.height)];
}

function mediaViewportMetrics() {
  const stageRect = ui.stage.getBoundingClientRect();
  const stageWidth = Math.max(1, Math.round(stageRect.width));
  const stageHeight = Math.max(1, Math.round(stageRect.height));
  const [mediaWidth, mediaHeight] = activeMediaSize();
  if (!mediaWidth || !mediaHeight) {
    return {
      stageWidth,
      stageHeight,
      mediaWidth: stageWidth,
      mediaHeight: stageHeight,
      drawWidth: stageWidth,
      drawHeight: stageHeight,
      offsetX: 0,
      offsetY: 0,
    };
  }
  const scale = Math.min(stageWidth / mediaWidth, stageHeight / mediaHeight);
  const drawWidth = mediaWidth * scale;
  const drawHeight = mediaHeight * scale;
  return {
    stageWidth,
    stageHeight,
    mediaWidth,
    mediaHeight,
    drawWidth,
    drawHeight,
    offsetX: (stageWidth - drawWidth) / 2,
    offsetY: (stageHeight - drawHeight) / 2,
  };
}

function syncOverlaySize() {
  const metrics = mediaViewportMetrics();
  ui.overlay.width = metrics.stageWidth;
  ui.overlay.height = metrics.stageHeight;
}

function mediaToOverlay(point) {
  if (!Array.isArray(point) || point.length !== 2) return null;
  const metrics = mediaViewportMetrics();
  return [
    metrics.offsetX + (Number(point[0]) / metrics.mediaWidth) * metrics.drawWidth,
    metrics.offsetY + (Number(point[1]) / metrics.mediaHeight) * metrics.drawHeight,
  ];
}

function overlayToMedia(point) {
  if (!Array.isArray(point) || point.length !== 2) return null;
  const metrics = mediaViewportMetrics();
  const localX = Number(point[0]) - metrics.offsetX;
  const localY = Number(point[1]) - metrics.offsetY;
  if (localX < 0 || localY < 0 || localX > metrics.drawWidth || localY > metrics.drawHeight) {
    return null;
  }
  return [
    (localX / metrics.drawWidth) * metrics.mediaWidth,
    (localY / metrics.drawHeight) * metrics.mediaHeight,
  ];
}

function overlayToMediaClamped(point) {
  if (!Array.isArray(point) || point.length !== 2) return null;
  const metrics = mediaViewportMetrics();
  const localX = Math.min(metrics.drawWidth, Math.max(0, Number(point[0]) - metrics.offsetX));
  const localY = Math.min(metrics.drawHeight, Math.max(0, Number(point[1]) - metrics.offsetY));
  return [
    (localX / metrics.drawWidth) * metrics.mediaWidth,
    (localY / metrics.drawHeight) * metrics.mediaHeight,
  ];
}

function findNearestCalibrationPointIndex(event, maxDistancePx = 18) {
  const points = appConfig?.calibration?.points || [];
  if (!points.length) return null;
  const rect = ui.overlay.getBoundingClientRect();
  const ox = event.clientX - rect.left;
  const oy = event.clientY - rect.top;
  let bestIndex = null;
  let bestDistance = Infinity;
  points.forEach((point, index) => {
    const mapped = mediaToOverlay(point.pixel);
    if (!mapped) return;
    const dx = mapped[0] - ox;
    const dy = mapped[1] - oy;
    const distance = Math.hypot(dx, dy);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  if (bestIndex === null || bestDistance > maxDistancePx) return null;
  return bestIndex;
}

function findNearestStampRegionPointIndex(event, maxDistancePx = 18) {
  const points = appConfig?.vision?.paper_roi_points || [];
  if (!points.length) return null;
  const rect = ui.overlay.getBoundingClientRect();
  const ox = event.clientX - rect.left;
  const oy = event.clientY - rect.top;
  let bestIndex = null;
  let bestDistance = Infinity;
  points.slice(0, 4).forEach((point, index) => {
    if (!Array.isArray(point) || point.length !== 2) return;
    const mapped = mediaToOverlay(point);
    if (!mapped) return;
    const dx = mapped[0] - ox;
    const dy = mapped[1] - oy;
    const distance = Math.hypot(dx, dy);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  if (bestIndex === null || bestDistance > maxDistancePx) return null;
  return bestIndex;
}

function distancePointToSegment(point, a, b) {
  const px = point[0];
  const py = point[1];
  const ax = a[0];
  const ay = a[1];
  const bx = b[0];
  const by = b[1];
  const dx = bx - ax;
  const dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  if (lenSq <= 1e-9) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq));
  const x = ax + t * dx;
  const y = ay + t * dy;
  return Math.hypot(px - x, py - y);
}

function findNearestStampRegionEdgeIndex(event, maxDistancePx = 12) {
  const points = (appConfig?.vision?.paper_roi_points || []).slice(0, 4);
  if (points.length !== 4 || points.some((point) => !Array.isArray(point))) return null;
  const rect = ui.overlay.getBoundingClientRect();
  const overlayPoint = [event.clientX - rect.left, event.clientY - rect.top];
  const mapped = points.map((point) => mediaToOverlay(point));
  if (mapped.some((point) => !point)) return null;
  let bestIndex = null;
  let bestDistance = Infinity;
  for (let index = 0; index < 4; index += 1) {
    const a = mapped[index];
    const b = mapped[(index + 1) % 4];
    const distance = distancePointToSegment(overlayPoint, a, b);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }
  if (bestIndex === null || bestDistance > maxDistancePx) return null;
  return bestIndex;
}

function drawCross(point, color, radius = 10) {
  const mapped = mediaToOverlay(point);
  if (!mapped) return;
  const [x, y] = mapped;
  const ctx = ui.overlay.getContext("2d");
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - radius * 1.8, y);
  ctx.lineTo(x + radius * 1.8, y);
  ctx.moveTo(x, y - radius * 1.8);
  ctx.lineTo(x, y + radius * 1.8);
  ctx.stroke();
}

function orderQuad(points) {
  if (!Array.isArray(points) || points.length !== 4) return null;
  const normalized = points
    .map((point) => [Number(point?.[0]), Number(point?.[1])])
    .filter((point) => Number.isFinite(point[0]) && Number.isFinite(point[1]));
  if (normalized.length !== 4) return null;
  const sums = normalized.map((point) => point[0] + point[1]);
  const diffs = normalized.map((point) => point[0] - point[1]);
  const topLeft = normalized[sums.indexOf(Math.min(...sums))];
  const bottomRight = normalized[sums.indexOf(Math.max(...sums))];
  const topRight = normalized[diffs.indexOf(Math.max(...diffs))];
  const bottomLeft = normalized[diffs.indexOf(Math.min(...diffs))];
  return [topLeft, topRight, bottomRight, bottomLeft];
}

function orderQuadEntries(points) {
  if (!Array.isArray(points) || points.length !== 4) return null;
  const entries = points
    .map((point, index) => ({
      index,
      point: [Number(point?.[0]), Number(point?.[1])],
    }))
    .filter((entry) => Number.isFinite(entry.point[0]) && Number.isFinite(entry.point[1]));
  if (entries.length !== 4) return null;
  const sums = entries.map((entry) => entry.point[0] + entry.point[1]);
  const diffs = entries.map((entry) => entry.point[0] - entry.point[1]);
  const topLeft = entries[sums.indexOf(Math.min(...sums))];
  const bottomRight = entries[sums.indexOf(Math.max(...sums))];
  const topRight = entries[diffs.indexOf(Math.max(...diffs))];
  const bottomLeft = entries[diffs.indexOf(Math.min(...diffs))];
  return [topLeft, topRight, bottomRight, bottomLeft];
}

function calibrationClockwiseIndices() {
  const points = (appConfig?.calibration?.points || []).map((point, index) => ({
    index,
    pixel: point.pixel,
  }));
  if (!points.length) return [];
  if (points.length !== 4 || points.some((point) => !Array.isArray(point.pixel) || point.pixel.length !== 2)) {
    return points.map((point) => point.index);
  }
  const sums = points.map((point) => Number(point.pixel[0]) + Number(point.pixel[1]));
  const diffs = points.map((point) => Number(point.pixel[0]) - Number(point.pixel[1]));
  const topLeft = points[sums.indexOf(Math.min(...sums))]?.index;
  const topRight = points[diffs.indexOf(Math.max(...diffs))]?.index;
  const bottomRight = points[sums.indexOf(Math.max(...sums))]?.index;
  const bottomLeft = points[diffs.indexOf(Math.min(...diffs))]?.index;
  const ordered = [topLeft, topRight, bottomRight, bottomLeft].filter((value) => Number.isInteger(value));
  const unique = [...new Set(ordered)];
  if (unique.length !== points.length) return points.map((point) => point.index);
  return unique;
}

function nextCalibrationIndexClockwise(currentIndex) {
  const points = appConfig?.calibration?.points || [];
  if (!points.length) return 0;
  const clockwise = calibrationClockwiseIndices();
  const now = Number(currentIndex) || 0;
  const position = clockwise.indexOf(now);
  if (position < 0) return (now + 1) % points.length;
  return clockwise[(position + 1) % clockwise.length];
}

function drawQuad(points, strokeStyle, fillStyle = "transparent", lineWidth = 2, dashed = false) {
  const quad = orderQuad(points);
  if (!quad) return;
  const mapped = quad.map((point) => mediaToOverlay(point));
  if (mapped.some((point) => !point || !Number.isFinite(point[0]) || !Number.isFinite(point[1]))) return;
  const ctx = ui.overlay.getContext("2d");
  ctx.save();
  ctx.strokeStyle = strokeStyle;
  ctx.fillStyle = fillStyle;
  ctx.lineWidth = lineWidth;
  if (dashed) ctx.setLineDash([8, 6]);
  ctx.beginPath();
  ctx.moveTo(mapped[0][0], mapped[0][1]);
  for (let index = 1; index < mapped.length; index += 1) {
    ctx.lineTo(mapped[index][0], mapped[index][1]);
  }
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawPath(points, strokeStyle, lineWidth = 2, dashed = false) {
  if (!Array.isArray(points) || points.length < 2) return;
  const mapped = points.map((point) => mediaToOverlay(point)).filter(Boolean);
  if (mapped.length < 2) return;
  const ctx = ui.overlay.getContext("2d");
  ctx.save();
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = lineWidth;
  if (dashed) ctx.setLineDash([8, 6]);
  ctx.beginPath();
  ctx.moveTo(mapped[0][0], mapped[0][1]);
  for (let index = 1; index < mapped.length; index += 1) {
    ctx.lineTo(mapped[index][0], mapped[index][1]);
  }
  ctx.stroke();
  ctx.restore();
}

function drawParallelRegionGuides(points) {
  const quad = orderQuad(points);
  if (!quad) return;
  const mapped = quad.map((point) => mediaToOverlay(point));
  if (mapped.some((point) => !point)) return;
  const ctx = ui.overlay.getContext("2d");
  const extend = 28;
  ctx.save();
  ctx.strokeStyle = "rgba(210, 40, 40, 0.34)";
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 5]);
  for (let index = 0; index < 4; index += 1) {
    const a = mapped[index];
    const b = mapped[(index + 1) % 4];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    if (length <= 1e-6) continue;
    const ux = dx / length;
    const uy = dy / length;
    ctx.beginPath();
    ctx.moveTo(a[0] - ux * extend, a[1] - uy * extend);
    ctx.lineTo(b[0] + ux * extend, b[1] + uy * extend);
    ctx.stroke();
  }
  ctx.restore();
}

function drawOverlay() {
  const ctx = ui.overlay.getContext("2d");
  ctx.clearRect(0, 0, ui.overlay.width, ui.overlay.height);
  if (cameraMode === "off") {
    return;
  }
  if (ui.crosshair.checked && cameraMode !== "off") {
    const metrics = mediaViewportMetrics();
    ctx.strokeStyle = "rgba(30, 90, 120, 0.45)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(metrics.offsetX + metrics.drawWidth / 2, metrics.offsetY);
    ctx.lineTo(metrics.offsetX + metrics.drawWidth / 2, metrics.offsetY + metrics.drawHeight);
    ctx.moveTo(metrics.offsetX, metrics.offsetY + metrics.drawHeight / 2);
    ctx.lineTo(metrics.offsetX + metrics.drawWidth, metrics.offsetY + metrics.drawHeight / 2);
    ctx.stroke();
  }

  const calibrationPixels = (appConfig?.calibration?.points || [])
    .map((point) => point.pixel)
    .filter((pixel) => Array.isArray(pixel) && pixel.length === 2);
  if (showCalibrationOverlay && cameraMode !== "document" && calibrationPixels.length >= 2) {
    // show progressive calibration path while selecting anchors
    drawPath(calibrationPixels, "rgba(33, 111, 198, 0.9)", 3, true);
  }
  if (showCalibrationOverlay && cameraMode !== "document" && calibrationPixels.length === 4) {
    // final calibrated plane feedback: thick dashed rectangle
    drawQuad(calibrationPixels, "rgba(33, 111, 198, 1)", "rgba(33, 111, 198, 0.10)", 4, true);
  }

  const paperRoiPixels = (appConfig?.vision?.paper_roi_points || [])
    .slice(0, 4)
    .filter((pixel) => Array.isArray(pixel) && pixel.length === 2);
  if (showStampRegionOverlay && cameraMode !== "document" && paperRoiPixels.length >= 2) {
    drawPath(paperRoiPixels, "rgba(210, 40, 40, 0.98)", 1.5, false);
  }
  if (showStampRegionOverlay && cameraMode !== "document" && paperRoiPixels.length === 4) {
    drawQuad(paperRoiPixels, "rgba(210, 40, 40, 0.98)", "transparent", 1.5, false);
    drawParallelRegionGuides(paperRoiPixels);
  }

  if (
    cameraMode !== "document"
    && detectedPaper?.found
    && Date.now() <= detectedPaperVisibleUntil
    && Array.isArray(detectedPaper.quad)
    && detectedPaper.quad.length === 4
  ) {
    drawQuad(detectedPaper.quad, "rgba(31, 122, 104, 0.98)", "transparent", 3, false);
    const orderedPaper = orderQuad(detectedPaper.quad) || [];
    orderedPaper.forEach((point) => drawCross(point, "rgba(31, 122, 104, 0.98)", 7));
  }

  if (showCalibrationOverlay && appConfig?.calibration?.points && cameraMode !== "document") {
    appConfig.calibration.points.forEach((point, index) => {
      const active = index === Number(ui.activeCalPoint.value || 0);
      drawCross(point.pixel, active ? "#c93a3a" : "#657386", active ? 10 : 7);
    });
  }
  if (showStampRegionOverlay && appConfig?.vision?.paper_roi_points && cameraMode !== "document") {
    appConfig.vision.paper_roi_points.slice(0, 4).forEach((point, index) => {
      if (!Array.isArray(point)) return;
      const active = index === Number(ui.activePaperRoiPoint?.value || 0);
      drawCross(point, active ? "#c93a3a" : "#8f2b2b", active ? 10 : 7);
    });
  }
  if (cameraMode !== "document" && selectedPixel) drawCross(selectedPixel, "#1f7a68", 9);
  if (cameraMode === "document" && documentPixel) drawCross(documentPixel, "#1f7a68", 9);
  if (targetPixel) drawCross(targetPixel, "#1647a6", 12);
}

function pointFromEvent(event) {
  const rect = ui.overlay.getBoundingClientRect();
  const overlayPoint = [event.clientX - rect.left, event.clientY - rect.top];
  return overlayToMedia(overlayPoint);
}

async function loadConfig() {
  const result = await api("/api/config");
  appConfig = result.config;
  runtimeBounds = result.runtime_bounds || null;
  boundsCapture = cloneBoundsCaptured(runtimeBounds?.captured);
  hydrateConfigInputs();
  renderCalibration();
  renderPaperRoi();
  updateModeUI();
  updateBoundsReadout();
  setStatus("Ready");
  log("Config loaded");
}

function hydrateConfigInputs() {
  ui.cameraWidth.value = appConfig.camera.width_px || 1280;
  ui.cameraHeight.value = appConfig.camera.height_px || 720;
  ui.cameraDistance.value = appConfig.camera.height_mm || 420;
  ui.cameraSource.value = appConfig.camera.media_source || "local";
  ui.streamUrl.value = appConfig.camera.stream_url || "";
  ui.serialBaudrate.value = appConfig.serial.baudrate || 115200;
  ui.serialDryRun.checked = Boolean(appConfig.serial.dry_run);
  fillSelect(ui.serialPort, [{ value: appConfig.serial.port, label: `${appConfig.serial.port} (configured)` }]);
  fillSelect(ui.flashPort, [{ value: appConfig.serial.port, label: `${appConfig.serial.port} (configured)` }]);
  ui.rollerLength.value = appConfig.paper_feed?.feed_length_mm || 35;
  ui.cameraDevice.innerHTML = "";
  const deviceOption = document.createElement("option");
  deviceOption.value = appConfig.camera.browser_device_id || "";
  deviceOption.textContent = appConfig.camera.browser_device_id ? "Configured camera" : "Default camera";
  ui.cameraDevice.appendChild(deviceOption);
  updateCameraSourceFields();
  hydrateMotionCalibrationInputs();
}

function hydrateMotionCalibrationInputs() {
  const axes = appConfig?.machine?.axes || {};
  ui.axisXScale.value = Number(axes.x?.actual_mm_per_commanded_mm ?? 1).toFixed(4);
  ui.axisYScale.value = Number(axes.y?.actual_mm_per_commanded_mm ?? 1).toFixed(4);
  ui.axisZScale.value = Number(axes.z?.actual_mm_per_commanded_mm ?? 1).toFixed(4);
  refreshMotionCalibrationReadout();
}

function fillSelect(select, items) {
  select.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  });
}

function renderCalibration() {
  const previous = ui.activeCalPoint.value;
  ui.activeCalPoint.innerHTML = "";
  ui.calibrationTable.innerHTML = "";
  (appConfig.calibration.points || []).forEach((point, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = point.label;
    ui.activeCalPoint.appendChild(option);

    const row = document.createElement("div");
    row.className = "cal-row";
    row.innerHTML = `
      <strong>${point.label}</strong>
      <span>px ${fmtPoint(point.pixel)}</span>
      <span>mm ${fmtPoint(point.real_mm)}</span>
    `;
    ui.calibrationTable.appendChild(row);
  });
  const hasPrevious = (appConfig.calibration.points || []).some((_, index) => String(index) === previous);
  if (hasPrevious) {
    ui.activeCalPoint.value = previous;
  } else if ((appConfig.calibration.points || []).length) {
    ui.activeCalPoint.value = "0";
  }
}

function ensurePaperRoiPoints() {
  if (!appConfig.vision || typeof appConfig.vision !== "object") appConfig.vision = {};
  if (!Array.isArray(appConfig.vision.paper_roi_points)) appConfig.vision.paper_roi_points = [];
  while (appConfig.vision.paper_roi_points.length < 4) {
    appConfig.vision.paper_roi_points.push(null);
  }
  if (!Array.isArray(appConfig.vision.stamp_region_machine_points)) appConfig.vision.stamp_region_machine_points = [];
  while (appConfig.vision.stamp_region_machine_points.length < 4) {
    appConfig.vision.stamp_region_machine_points.push(null);
  }
  return appConfig.vision.paper_roi_points;
}

function paperRoiComplete() {
  const points = appConfig?.vision?.paper_roi_points || [];
  return points.length >= 4 && points.slice(0, 4).every((point) => (
    Array.isArray(point)
    && point.length === 2
    && Number.isFinite(Number(point[0]))
    && Number.isFinite(Number(point[1]))
  ));
}

function requireStampDetectRegion() {
  if (!paperRoiComplete()) {
    throw new Error("Set and save the Stamp/Detect Region first");
  }
}

function activeStampRegionCornerIndex() {
  const motionPanelActive = $("#motionPanel")?.classList.contains("active");
  const select = motionPanelActive ? ui.activeStampRegionBoundPoint : ui.activePaperRoiPoint;
  if (!select) return Math.max(0, Math.min(3, stampRegionDrawIndex));
  return Math.max(0, Math.min(3, Number(select?.value || 0)));
}

function syncStampRegionCornerSelects(index) {
  const value = String(Math.max(0, Math.min(3, Number(index) || 0)));
  stampRegionDrawIndex = Number(value);
  if (ui.activePaperRoiPoint) ui.activePaperRoiPoint.value = value;
  if (ui.activeStampRegionBoundPoint) ui.activeStampRegionBoundPoint.value = value;
  drawOverlay();
}

function renderPaperRoi() {
  if (!ui.paperRoiTable) return;
  const previous = ui.activePaperRoiPoint?.value || ui.activeStampRegionBoundPoint?.value || String(stampRegionDrawIndex);
  const points = ensurePaperRoiPoints();
  const machinePoints = appConfig.vision.stamp_region_machine_points || [];
  if (ui.activePaperRoiPoint) ui.activePaperRoiPoint.innerHTML = "";
  if (ui.activeStampRegionBoundPoint) ui.activeStampRegionBoundPoint.innerHTML = "";
  ui.paperRoiTable.innerHTML = "";
  if (ui.stampRegionBoundTable) ui.stampRegionBoundTable.innerHTML = "";
  paperRoiLabels.forEach((label, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = label;
    if (ui.activePaperRoiPoint) ui.activePaperRoiPoint.appendChild(option);
    if (ui.activeStampRegionBoundPoint) {
      const boundOption = document.createElement("option");
      boundOption.value = String(index);
      boundOption.textContent = label;
      ui.activeStampRegionBoundPoint.appendChild(boundOption);
    }

    const row = document.createElement("div");
    row.className = "cal-row";
    row.innerHTML = `
      <strong>${label}</strong>
      <span>px ${fmtPoint(points[index])}</span>
      <span>machine ${fmtPoint(machinePoints[index])}</span>
    `;
    ui.paperRoiTable.appendChild(row);

    if (ui.stampRegionBoundTable) {
      const boundRow = document.createElement("div");
      boundRow.className = "cal-row";
      boundRow.innerHTML = `
        <strong>${label}</strong>
        <span>px ${fmtPoint(points[index])}</span>
        <span>machine ${fmtPoint(machinePoints[index])}</span>
      `;
      ui.stampRegionBoundTable.appendChild(boundRow);
    }
  });
  syncStampRegionCornerSelects(paperRoiLabels[Number(previous)] ? previous : "0");
}

function toggleCalibrationOverlay() {
  showCalibrationOverlay = !showCalibrationOverlay;
  const button = $("#toggleCalibrationOverlayBtn");
  if (button) button.textContent = showCalibrationOverlay ? "Disable" : "Enable";
  if (showCalibrationOverlay) cameraEditTarget = "calibration";
  drawOverlay();
}

function toggleStampRegionOverlay() {
  showStampRegionOverlay = !showStampRegionOverlay;
  const button = $("#toggleStampRegionOverlayBtn");
  if (button) button.textContent = showStampRegionOverlay ? "Disable" : "Enable";
  if (showStampRegionOverlay) cameraEditTarget = "region";
  drawOverlay();
}

function startStampRegionDraw() {
  ensurePaperRoiPoints();
  const [mediaWidth, mediaHeight] = activeMediaSize();
  const marginX = Math.max(24, mediaWidth * 0.16);
  const marginY = Math.max(24, mediaHeight * 0.16);
  appConfig.vision.paper_roi_points = [
    [marginX, marginY],
    [mediaWidth - marginX, marginY],
    [mediaWidth - marginX, mediaHeight - marginY],
    [marginX, mediaHeight - marginY],
  ];
  stampRegionDrawIndex = 0;
  cameraEditTarget = "region";
  showStampRegionOverlay = true;
  const button = $("#toggleStampRegionOverlayBtn");
  if (button) button.textContent = "Disable";
  renderPaperRoi();
  drawOverlay();
  setStatus("Rectangle created. Drag corners or edges to adjust.");
}

function useCalibrationAsStampRegion() {
  const points = (appConfig?.calibration?.points || [])
    .map((point) => point.pixel)
    .filter((point) => Array.isArray(point) && point.length === 2);
  if (points.length < 4) {
    throw new Error("Set four camera calibration anchors first");
  }
  ensurePaperRoiPoints();
  appConfig.vision.paper_roi_points = orderQuad(points.slice(0, 4));
  showStampRegionOverlay = true;
  const button = $("#toggleStampRegionOverlayBtn");
  if (button) button.textContent = "Disable";
  renderPaperRoi();
  drawOverlay();
  setStatus("Stamp region copied from calibration");
}

function updateModeUI() {
  const mode = ui.workflowMode.value;
  ui.modeA.classList.toggle("hidden", mode !== "manual_repeat");
  ui.modeB.classList.toggle("hidden", mode !== "camera_repeat");
  ui.modeC.classList.toggle("hidden", mode !== "document_repeat");
  ui.targetActionButtons.classList.add("hidden");
}

function updateCameraSourceFields() {
  const stream = ui.cameraSource.value === "stream";
  ui.cameraDeviceField.classList.toggle("hidden", stream);
  ui.streamUrlField.classList.toggle("hidden", !stream);
}

async function refreshCameraDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    throw new Error("This webview does not support camera device listing");
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cameras = devices.filter((device) => device.kind === "videoinput");
  const items = [{ value: "", label: "Default camera" }].concat(
    cameras.map((device, index) => ({
      value: device.deviceId,
      label: device.label || `Camera ${index + 1}`,
    })),
  );
  fillSelect(ui.cameraDevice, items);
  ui.cameraDevice.value = appConfig.camera.browser_device_id || "";
  log("Camera devices refreshed", { count: cameras.length });
}

async function toggleCamera() {
  if (cameraSimulationPending) {
    cancelCameraSimulationPreview();
    return;
  }
  if (cameraSimulationActive) {
    cancelCameraSimulation();
    return;
  }
  if (liveCameraFrameReady()) {
    stopCamera();
    return;
  }
  if (ui.cameraSource.value === "stream") {
    startStreamCamera();
  } else {
    await startLocalCamera();
  }
}

async function startLocalCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This webview does not support browser camera access");
  }
  const width = Number(ui.cameraWidth.value) || 1280;
  const height = Number(ui.cameraHeight.value) || 720;
  const deviceId = ui.cameraDevice.value;
  const video = deviceId
    ? { deviceId: { exact: deviceId }, width: { ideal: width }, height: { ideal: height } }
    : { width: { ideal: width }, height: { ideal: height } };
  cameraStream = await navigator.mediaDevices.getUserMedia({ audio: false, video });
  if (cameraSimulationPending) {
    cancelCameraSimulationPreview();
  } else if (cameraSimulationActive) {
    cancelCameraSimulation();
  }
  ui.video.srcObject = cameraStream;
  ui.video.removeAttribute("src");
  await ui.video.play();
  ui.cameraStatus.textContent = "Local camera on";
  setCameraButtons(true, "Camera Off");
  setSimulationButtons(false);
  selectedPixel = null;
  documentPixel = null;
  updateStageMode("local-video");
}

function startStreamCamera() {
  const url = ui.streamUrl.value.trim();
  if (!url) throw new Error("Stream URL is empty");
  if (cameraSimulationPending) {
    cancelCameraSimulationPreview();
  } else if (cameraSimulationActive) {
    cancelCameraSimulation();
  }
  stopLocalTracks();
  selectedPixel = null;
  documentPixel = null;
  if (url.toLowerCase().endsWith(".mp4")) {
    ui.video.srcObject = null;
    ui.video.src = url;
    ui.video.play();
    updateStageMode("stream-video");
  } else {
    ui.image.src = url;
    updateStageMode("stream-image");
  }
  ui.cameraStatus.textContent = "Network stream on";
  setCameraButtons(true, "Camera Off");
  setSimulationButtons(false);
}

async function startCameraSimulationFromFile(file) {
  if (!file) return;
  const imageData = await fileToDataUrl(file);
  if (!cameraSimulationActive && !cameraSimulationPending) {
    cameraModeBeforeSimulation = cameraMode;
    imageSrcBeforeSimulation = ui.image.getAttribute("src") || "";
  }
  cameraSimulationPending = true;
  pendingSimulationImageData = imageData;
  pendingSimulationName = file.name;
  cameraSimulationActive = false;
  selectedPixel = null;
  targetPixel = null;
  detectedPaper = null;
  ui.image.onload = () => {
    updateStageMode("simulation-pending");
    syncOverlaySize();
    drawOverlay();
  };
  ui.image.src = imageData;
  ui.cameraStatus.textContent = `Simulation preview: ${file.name}`;
  ui.cameraSimulationAdjustLabel.textContent = `Preview: ${file.name}`;
  ui.cameraSimulationAdjust?.classList.remove("hidden");
  setCameraButtons(liveCameraFrameReady(), liveCameraFrameReady() ? "Camera Off" : "Camera On");
  setSimulationButtons(false);
  setStatus("Rotate simulation photo, then confirm");
  log("Camera simulation preview loaded", { filename: file.name, size: file.size });
}

function toggleCameraSimulationPicker() {
  if (cameraSimulationPending) {
    cancelCameraSimulationPreview();
    return;
  }
  if (cameraSimulationActive || cameraMode === "simulation-image") {
    cancelCameraSimulation();
    return;
  }
  ui.cameraSimulationFile?.click();
}

async function rotateSimulationPreview(clockwise = true) {
  if (!cameraSimulationPending || !pendingSimulationImageData) return;
  const image = await loadImageFromDataUrl(pendingSimulationImageData);
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalHeight;
  canvas.height = image.naturalWidth;
  const ctx = canvas.getContext("2d");
  ctx.save();
  if (clockwise) {
    ctx.translate(canvas.width, 0);
    ctx.rotate(Math.PI / 2);
  } else {
    ctx.translate(0, canvas.height);
    ctx.rotate(-Math.PI / 2);
  }
  ctx.drawImage(image, 0, 0);
  ctx.restore();
  pendingSimulationImageData = canvas.toDataURL("image/jpeg", 0.92);
  ui.image.onload = () => {
    updateStageMode("simulation-pending");
    syncOverlaySize();
    drawOverlay();
  };
  ui.image.src = pendingSimulationImageData;
  setStatus("Simulation photo rotated");
}

function confirmCameraSimulation() {
  if (!cameraSimulationPending || !pendingSimulationImageData) return;
  cameraSimulationPending = false;
  ui.cameraSimulationAdjust?.classList.add("hidden");
  selectedPixel = null;
  targetPixel = null;
  detectedPaper = null;
  ui.image.onload = () => {
    updateStageMode("simulation-image");
    syncOverlaySize();
    drawOverlay();
  };
  ui.image.src = pendingSimulationImageData;
  updateStageMode("simulation-image");
  ui.cameraStatus.textContent = `Simulation: ${pendingSimulationName || "photo"}`;
  setCameraButtons(liveCameraFrameReady(), liveCameraFrameReady() ? "Camera Off" : "Camera On");
  setSimulationButtons(true);
  setStatus("Camera simulation confirmed");
  log("Camera simulation confirmed", { filename: pendingSimulationName || "photo" });
}

function cancelCameraSimulationPreview() {
  cameraSimulationPending = false;
  pendingSimulationImageData = "";
  pendingSimulationName = "";
  ui.cameraSimulationAdjust?.classList.add("hidden");
  restoreCameraViewAfterSimulation("Camera simulation preview canceled");
}

function cancelCameraSimulation() {
  cameraSimulationPending = false;
  pendingSimulationImageData = "";
  pendingSimulationName = "";
  ui.cameraSimulationAdjust?.classList.add("hidden");
  restoreCameraViewAfterSimulation("Camera simulation canceled");
}

function restoreCameraViewAfterSimulation(message) {
  const restoreMode = cameraModeBeforeSimulation || "off";
  setSimulationButtons(false);
  detectedPaper = null;
  ui.image.onload = null;

  if (restoreMode === "local-video" && cameraStream) {
    ui.cameraStatus.textContent = "Local camera on";
    setCameraButtons(true, "Camera Off");
    updateStageMode("local-video");
  } else if (restoreMode === "stream-video" && ui.video.getAttribute("src")) {
    ui.cameraStatus.textContent = "Network stream on";
    setCameraButtons(true, "Camera Off");
    updateStageMode("stream-video");
  } else if (restoreMode === "stream-image" && imageSrcBeforeSimulation) {
    ui.image.onload = () => {
      updateStageMode("stream-image");
      syncOverlaySize();
      drawOverlay();
    };
    ui.image.src = imageSrcBeforeSimulation;
    ui.cameraStatus.textContent = "Network stream on";
    setCameraButtons(true, "Camera Off");
  } else if (restoreMode === "document" && imageSrcBeforeSimulation) {
    ui.image.onload = () => {
      updateStageMode("document");
      syncOverlaySize();
      drawOverlay();
    };
    ui.image.src = imageSrcBeforeSimulation;
    ui.cameraStatus.textContent = "Document preview";
    setCameraButtons(false);
  } else {
    ui.image.removeAttribute("src");
    ui.cameraStatus.textContent = "Off";
    setCameraButtons(false);
    updateStageMode("off");
  }

  cameraModeBeforeSimulation = "off";
  imageSrcBeforeSimulation = "";
  setStatus(message);
  log(message);
}

function stopLocalTracks() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
  }
  cameraStream = null;
}

function stopCamera() {
  stopLocalTracks();
  cameraSimulationActive = false;
  cameraSimulationPending = false;
  documentPreviewActive = false;
  cameraModeBeforeSimulation = "off";
  imageSrcBeforeSimulation = "";
  cameraModeBeforeDocument = "off";
  imageSrcBeforeDocument = "";
  pendingSimulationImageData = "";
  pendingSimulationName = "";
  ui.cameraSimulationAdjust?.classList.add("hidden");
  ui.video.pause();
  ui.video.removeAttribute("src");
  ui.video.srcObject = null;
  ui.image.removeAttribute("src");
  selectedPixel = null;
  documentPixel = null;
  targetPixel = null;
  detectedPaper = null;
  ui.cameraStatus.textContent = "Off";
  setCameraButtons(false);
  setSimulationButtons(false);
  updateStageMode("off");
  setStatus("Camera off");
}

async function saveCameraSetup(includeCalibration = false) {
  appConfig.camera.media_source = ui.cameraSource.value;
  appConfig.camera.browser_device_id = ui.cameraDevice.value;
  appConfig.camera.stream_url = ui.streamUrl.value.trim();
  appConfig.camera.width_px = Number(ui.cameraWidth.value);
  appConfig.camera.height_px = Number(ui.cameraHeight.value);
  appConfig.camera.height_mm = Number(ui.cameraDistance.value);

  const calibrationPoints = includeCalibration
    ? appConfig.calibration.points.map((point) => ({
        label: point.label,
        pixel: point.pixel,
        real_mm: point.real_mm,
      }))
    : null;

  const result = await api("/api/camera/setup", {
    method: "POST",
    body: JSON.stringify({
      index: appConfig.camera.index || 0,
      browser_device_id: appConfig.camera.browser_device_id,
      media_source: appConfig.camera.media_source,
      stream_url: appConfig.camera.stream_url,
      width_px: appConfig.camera.width_px,
      height_px: appConfig.camera.height_px,
      height_mm: appConfig.camera.height_mm,
      calibration_points: calibrationPoints,
    }),
  });
  appConfig = result.config;
  log("Camera settings saved");
  setStatus("Camera settings saved");
}

async function uploadCurrentRawFrame() {
  const imageData = captureCurrentFrameDataUrl();
  if (!imageData) return null;
  await api("/api/snapshot/upload", {
    method: "POST",
    body: JSON.stringify({ image_data: imageData }),
  });
  return true;
}

function captureCurrentFrameDataUrl() {
  const canvas = document.createElement("canvas");
  if (cameraMode === "local-video" || cameraMode === "stream-video") {
    if (!ui.video.videoWidth || !ui.video.videoHeight) return null;
    canvas.width = ui.video.videoWidth;
    canvas.height = ui.video.videoHeight;
    canvas.getContext("2d").drawImage(ui.video, 0, 0, canvas.width, canvas.height);
  } else if (cameraMode === "stream-image" || cameraMode === "simulation-image") {
    if (!ui.image.naturalWidth || !ui.image.naturalHeight) return null;
    canvas.width = ui.image.naturalWidth;
    canvas.height = ui.image.naturalHeight;
    canvas.getContext("2d").drawImage(ui.image, 0, 0, canvas.width, canvas.height);
  } else {
    return null;
  }
  return canvas.toDataURL("image/jpeg", 0.9);
}

function captureCurrentStageImageDataUrl({ includeDocument = false } = {}) {
  const canvas = document.createElement("canvas");
  if (cameraMode === "local-video" || cameraMode === "stream-video") {
    if (!ui.video.videoWidth || !ui.video.videoHeight) return null;
    canvas.width = ui.video.videoWidth;
    canvas.height = ui.video.videoHeight;
    canvas.getContext("2d").drawImage(ui.video, 0, 0, canvas.width, canvas.height);
  } else if (
    cameraMode === "stream-image"
    || cameraMode === "simulation-image"
    || (includeDocument && cameraMode === "document")
  ) {
    if (!ui.image.naturalWidth || !ui.image.naturalHeight) return null;
    canvas.width = ui.image.naturalWidth;
    canvas.height = ui.image.naturalHeight;
    canvas.getContext("2d").drawImage(ui.image, 0, 0, canvas.width, canvas.height);
  } else {
    return null;
  }
  return canvas.toDataURL("image/jpeg", 0.9);
}

function setDetectDebugPreview(result) {
  if (!ui.detectDebugImage || !ui.detectDebugMeta) return;
  const imageData = result?.debug_image_data;
  if (typeof imageData === "string" && imageData.startsWith("data:image/")) {
    ui.detectDebugImage.src = imageData;
  } else {
    ui.detectDebugImage.removeAttribute("src");
  }
  ui.detectDebugMeta.textContent = result?.message || "No debug image.";
}

async function detectPaper() {
  const uploaded = await uploadCurrentRawFrame();
  if (!uploaded) {
    throw new Error("Turn on camera before detecting paper");
  }

  const requestBody = {
    use_calibration_roi: false,
    use_paper_roi: true,
    paper_color: "auto",
  }
  let result = await api("/api/detect-paper", {
    method: "POST",
    body: JSON.stringify(requestBody),
  });

  if (!result?.found && (appConfig?.calibration?.points || []).length >= 4) {
    const roiBody = {
      use_calibration_roi: true,
      use_paper_roi: true,
      paper_color: "auto",
    }
    const roiRetry = await api("/api/detect-paper", {
      method: "POST",
      body: JSON.stringify(roiBody),
    });
    if (roiRetry?.found) {
      result = roiRetry;
      const { debug_image_data: _roiDbg, ...roiLog } = roiRetry || {};
      log("Region detected with calibration ROI", roiLog);
    }
  }

  detectedPaper = result;
  setDetectDebugPreview(result);

  detectedPaperVisibleUntil = Date.now() + 5000;
  if (detectedPaperTimer) {
    window.clearTimeout(detectedPaperTimer);
    detectedPaperTimer = null;
  }
  detectedPaperTimer = window.setTimeout(() => {
    detectedPaperVisibleUntil = 0;
    drawOverlay();
    detectedPaperTimer = null;
  }, 5100);
  drawOverlay();
  const { debug_image_data: _dbg, ...logResult } = result || {};
  log(result.found ? "Region detected" : "Region not found", logResult);
  setStatus(result.found ? "Region detected" : "Region not found");
}

async function uploadModeAFrame(stage) {
  const imageData = captureCurrentFrameDataUrl();
  if (!imageData) {
    throw new Error("Turn on camera or load Camera Simulation before running a cycle");
  }
  await api("/api/mode-a/frame", {
    method: "POST",
    body: JSON.stringify({ stage, image_data: imageData }),
  });
}

async function uploadDocument() {
  const file = ui.documentFile.files?.[0];
  if (!file) throw new Error("Choose a document first");
  if (cameraSimulationPending) {
    cancelCameraSimulationPreview();
  }
  if (!documentPreviewActive) {
    cameraModeBeforeDocument = cameraMode;
    imageSrcBeforeDocument = ui.image.getAttribute("src") || "";
  }
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/document", { method: "POST", body: form });
  if (!response.ok) throw new Error((await response.json()).detail || "Upload failed");
  documentInfo = await response.json();
  ui.image.src = `${documentInfo.preview_url}?t=${Date.now()}`;
  documentPixel = null;
  selectedPixel = null;
  targetPixel = null;
  documentPreviewActive = true;
  ui.image.onload = () => {
    updateStageMode("document");
    setStatus("Document loaded - click stamp point");
  };
  log("Document preview loaded", documentInfo);
}

function restoreStageAfterDocument(message = "Document selection canceled") {
  const restoreMode = cameraModeBeforeDocument || "off";
  documentPreviewActive = false;
  ui.image.onload = null;

  if (restoreMode === "local-video" && cameraStream) {
    ui.cameraStatus.textContent = "Local camera on";
    setCameraButtons(true, "Camera Off");
    setSimulationButtons(false);
    updateStageMode("local-video");
  } else if (restoreMode === "stream-video" && ui.video.getAttribute("src")) {
    ui.cameraStatus.textContent = "Network stream on";
    setCameraButtons(true, "Camera Off");
    setSimulationButtons(false);
    updateStageMode("stream-video");
  } else if ((restoreMode === "stream-image" || restoreMode === "simulation-image") && imageSrcBeforeDocument) {
    ui.image.onload = () => {
      updateStageMode(restoreMode);
      syncOverlaySize();
      drawOverlay();
    };
    ui.image.src = imageSrcBeforeDocument;
    ui.cameraStatus.textContent = restoreMode === "simulation-image" ? "Simulation" : "Network stream on";
    setCameraButtons(restoreMode !== "simulation-image", restoreMode === "simulation-image" ? "Camera On" : "Camera Off");
    setSimulationButtons(restoreMode === "simulation-image");
  } else {
    ui.image.removeAttribute("src");
    ui.cameraStatus.textContent = "Off";
    setCameraButtons(false);
    setSimulationButtons(false);
    updateStageMode("off");
  }

  cameraModeBeforeDocument = "off";
  imageSrcBeforeDocument = "";
  setStatus(message);
  log(message);
}

function cancelModeCSelection() {
  documentPixel = null;
  selectedPixel = null;
  if (documentPreviewActive) {
    restoreStageAfterDocument("Mode C selection canceled");
  } else {
    setStatus("No active Mode C selection");
  }
  drawOverlay();
}

async function confirmModeA() {
  requireStampDetectRegion();
  const statusResult = await api("/api/serial/query", { method: "POST", body: "{}" });
  renderSerialStatus(statusResult.status, statusResult.serial);
  const pos = currentWorkXYZ();
  if (pos.x === null || pos.y === null) {
    throw new Error("Cannot read current XY position from controller");
  }
  const realX = commandedDeltaToReal("x", pos.x);
  const realY = commandedDeltaToReal("y", pos.y);
  const preview = await api("/api/preview", {
    method: "POST",
    body: JSON.stringify({ source: "real", x: realX, y: realY, offset_mm: [0, 0] }),
  });
  setActiveJob({
    label: "Mode A manual-repeat",
    mode: "manual_repeat",
    targetPayload: { source: "real", x: realX, y: realY },
    relative_xy: preview.target.relative_xy,
  });
  renderPreview(preview);
}

async function confirmModeB() {
  requireStampDetectRegion();
  if (!selectedPixel) throw new Error("Click the stamp point in the camera view first");
  const preview = await api("/api/preview", {
    method: "POST",
    body: JSON.stringify({
      source: "pixel",
      x: selectedPixel[0],
      y: selectedPixel[1],
      offset_mm: [0, 0],
    }),
  });
  setActiveJob({
    label: "Mode B camera-repeat",
    mode: "camera_repeat",
    targetPayload: {
      source: "real",
      x: preview.target.real_xy_mm[0],
      y: preview.target.real_xy_mm[1],
    },
    relative_xy: preview.target.relative_xy,
  });
  renderPreview(preview);
}

async function confirmModeC() {
  if (!documentInfo || !documentPixel) throw new Error("Upload a document and click a stamp point first");
  const shouldRestore = documentPreviewActive;
  try {
    const width = Number(documentInfo.width_px) || ui.image.naturalWidth;
    const height = Number(documentInfo.height_px) || ui.image.naturalHeight;
    if (!width || !height) throw new Error("Document preview is not ready");

    const relative = [documentPixel[0] / width, documentPixel[1] / height];
    const confirmImageData = captureCurrentStageImageDataUrl({ includeDocument: true });
    confirmedModeCRelative = relative;
    confirmedModeCDocumentPixel = [...documentPixel];
    await renderModeCPositionPreview(relative, confirmedModeCDocumentPixel, confirmImageData);

    setActiveJob({
      label: `Mode C document-repeat: ${documentInfo.filename}`,
      mode: "document_repeat",
      targetPayload: { source: "relative_paper", x: relative[0], y: relative[1] },
      relative_xy: relative,
    });

    try {
      await previewJob();
    } catch (error) {
      // Confirming the file position should not depend on machine/stamp-region mapping.
      log(`Mode C target confirmed; machine preview skipped: ${error.message}`);
    }
  } finally {
    if (shouldRestore) {
      restoreStageAfterDocument("Mode C file position confirmed");
    }
  }
}

function loadImageFromDataUrl(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Cannot load debug image"));
    image.src = dataUrl;
  });
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Cannot read debug image file"));
    reader.readAsDataURL(file);
  });
}

async function renderModeCPositionPreview(relative, pixel, imageData = null) {
  if (!documentInfo || !relative || !pixel) return;
  const source = imageData || `${documentInfo.preview_url}?t=${Date.now()}`;
  const image = await loadImageFromDataUrl(source);
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(image, 0, 0);
  const radius = Math.max(10, Math.min(canvas.width, canvas.height) * 0.022);
  ctx.save();
  ctx.fillStyle = "rgba(220, 0, 0, 0.9)";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = Math.max(3, radius * 0.24);
  ctx.beginPath();
  ctx.arc(pixel[0], pixel[1], radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
  const rendered = canvas.toDataURL("image/jpeg", 0.92);
  ui.modeCConfirmPreview.src = rendered;
  ui.modeCConfirmMeta.textContent = `Confirmed ${documentInfo.filename}: relative ${fmtRelative(relative)}`;
  log("Mode C confirmed file position preview rendered", { relative_xy: relative, document_pixel: pixel });
}

function relativePointOnStampRegion(relative, imageWidth, imageHeight) {
  const rx = Math.max(0, Math.min(1, Number(relative?.[0])));
  const ry = Math.max(0, Math.min(1, Number(relative?.[1])));
  const region = orderQuad((appConfig?.vision?.paper_roi_points || []).slice(0, 4));
  if (!region) {
    return [rx * imageWidth, ry * imageHeight];
  }
  const configWidth = Number(appConfig?.camera?.width_px) || imageWidth;
  const configHeight = Number(appConfig?.camera?.height_px) || imageHeight;
  const sx = imageWidth / Math.max(1, configWidth);
  const sy = imageHeight / Math.max(1, configHeight);
  const scaled = region.map((point) => [Number(point[0]) * sx, Number(point[1]) * sy]);
  const [tl, tr, br, bl] = scaled;
  const top = [tl[0] + (tr[0] - tl[0]) * rx, tl[1] + (tr[1] - tl[1]) * rx];
  const bottom = [bl[0] + (br[0] - bl[0]) * rx, bl[1] + (br[1] - bl[1]) * rx];
  return [top[0] + (bottom[0] - top[0]) * ry, top[1] + (bottom[1] - top[1]) * ry];
}

async function debugModeCPreview() {
  if (!documentInfo || !confirmedModeCRelative) {
    throw new Error("Confirm a Mode C file position first");
  }
  const imageData = captureCurrentFrameDataUrl();
  if (!imageData) {
    throw new Error("Turn on camera or load Camera Simulation before debugging");
  }
  const result = await api("/api/document/match", {
    method: "POST",
    body: JSON.stringify({
      image_data: imageData,
      relative_xy: confirmedModeCRelative,
    }),
  });
  if (result.debug_image_data) {
    ui.modeCDebugPreview.src = result.debug_image_data;
  } else {
    ui.modeCDebugPreview.removeAttribute("src");
  }
  ui.modeCDebugMeta.textContent = result.found
    ? `${result.message} target ${fmtPoint(result.target_pixel)}`
    : result.message || "Document match failed.";
  log(result.found ? "Mode C document matched" : "Mode C document match failed", result);
}

function setActiveJob(job) {
  activeJob = job;
  readout.job.textContent = job ? job.label : "-";
  readout.relative.textContent = job ? fmtRelative(job.relative_xy) : "-";
}

function jobPayload() {
  if (!activeJob) throw new Error("Confirm a target first");
  return {
    ...(activeJob.targetPayload || {
      source: "relative_paper",
      x: activeJob.relative_xy[0],
      y: activeJob.relative_xy[1],
    }),
    offset_mm: [Number($("#offsetX").value), Number($("#offsetY").value)],
    paper_quad: activeJob?.targetPayload?.source === "relative_paper" && detectedPaper?.found ? detectedPaper.quad : null,
  };
}

function renderPreview(result) {
  const target = result.target || result.preview?.target;
  const gcode = result.gcode || result.preview?.gcode || [];
  if (!target) return;
  targetPixel = target.pixel_xy;
  readout.pixel.textContent = fmtPoint(target.pixel_xy);
  readout.paper.textContent = fmtPoint(target.paper_xy_mm);
  readout.real.textContent = fmtPoint(target.real_xy_mm);
  readout.command.textContent = fmtPoint(target.commanded_xy_mm);
  ui.gcode.textContent = gcode.join("\n");
  drawOverlay();
}

async function previewJob() {
  const result = await api("/api/preview", { method: "POST", body: JSON.stringify(jobPayload()) });
  renderPreview(result);
  log("Job preview updated", result.target);
}

async function moveJobSlow() {
  const result = await api("/api/move", {
    method: "POST",
    body: JSON.stringify({ ...jobPayload(), slow: true }),
  });
  renderPreview(result.preview);
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(5, 180);
  log("Move command sent", result.serial);
}

async function stampJob(dryRun) {
  const result = await api("/api/stamp", {
    method: "POST",
    body: JSON.stringify({ ...jobPayload(), dry_run: dryRun }),
  });
  renderPreview(result.preview);
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(6, 180);
  log(dryRun ? "Dry stamp complete" : "Live stamp command sent", result.serial);
}

function modeACyclePayload() {
  if (!activeJob) {
    throw new Error("Confirm a mode target first");
  }
  const mode = activeJob.mode || ui.workflowMode.value;
  const target = jobPayload();
  return {
    ...target,
    detect_paper: mode !== "manual_repeat",
    feed_before: false,
    feed_after: true,
    return_xy_zero: true,
    dry_run: false,
  };
}

async function runModeACycleOnce() {
  requireStampDetectRegion();
  if (!activeJob) throw new Error("Confirm a target first");
  const mode = activeJob.mode || ui.workflowMode.value;
  if (mode !== "manual_repeat") {
    await goZero("xy");
    await uploadModeAFrame("before");
  }
  const cycle = await api("/api/repeat/cycle", {
    method: "POST",
    body: JSON.stringify(modeACyclePayload()),
  });
  renderPreview({ target: cycle.target, gcode: cycle.gcode });
  renderSerialStatus(cycle.status, cycle.serial_chunks?.[cycle.serial_chunks.length - 1]?.serial || null);
  if (Array.isArray(cycle.serial_chunks)) {
    cycle.serial_chunks.forEach((chunk) => log(`Mode A ${chunk.stage}`, chunk.serial));
  }
  requestStatusBurst(6, 180);
  if (mode !== "manual_repeat") {
    await uploadModeAFrame("after");
  }
  setStatus(`${activeJob.label || "Repeat"} run complete`);
}

function clearTarget() {
  selectedPixel = null;
  documentPixel = null;
  targetPixel = null;
  activeJob = null;
  confirmedModeCRelative = null;
  confirmedModeCDocumentPixel = null;
  if (ui.modeCConfirmPreview) ui.modeCConfirmPreview.removeAttribute("src");
  if (ui.modeCDebugPreview) ui.modeCDebugPreview.removeAttribute("src");
  if (ui.modeCConfirmMeta) ui.modeCConfirmMeta.textContent = "No confirmed file position yet.";
  if (ui.modeCDebugMeta) ui.modeCDebugMeta.textContent = "No debug run yet.";
  [readout.job, readout.relative, readout.pixel, readout.paper, readout.real, readout.command].forEach((el) => {
    el.textContent = "-";
  });
  ui.gcode.textContent = "";
  drawOverlay();
  log("Target cleared");
}

async function scanSerialPorts() {
  const result = await api("/api/serial/ports");
  const items = (result.ports || []).map((port) => ({
    value: port.device,
    label: `${port.device} ${port.description || ""}`.trim(),
  }));
  if (!items.length) items.push({ value: appConfig.serial.port, label: `${appConfig.serial.port} (configured)` });
  fillSelect(ui.serialPort, items);
  fillSelect(ui.flashPort, items);
  renderSerialStatus(result.status);
  log("Serial ports scanned", result.ports || []);
}

function renderSerialStatus(status = {}, serial = null) {
  const connected = Boolean(status.connected);
  const stateText = status.state || (connected ? "connected" : "disconnected");
  const portText = status.port || ui.serialPort.value || appConfig?.serial?.port || "-";
  readout.serialConnection.textContent = stateText;
  readout.serialPort.textContent = portText;
  readout.motionConnState.textContent = stateText;
  readout.motionConnPort.textContent = portText;
  if (ui.motionConnectBtn) ui.motionConnectBtn.textContent = connected ? "Disconnect" : "Connect";
  const pos = status.position || {};
  const prevW = currentWorkXYZ();
  const mRaw = Array.isArray(pos.mpos) && pos.mpos.length >= 3 ? pos.mpos.map(Number) : null;
  const wRaw = Array.isArray(pos.wpos) && pos.wpos.length >= 3 ? pos.wpos.map(Number) : null;
  const wcoRaw = Array.isArray(pos.wco) && pos.wco.length >= 3 ? pos.wco.map(Number) : null;

  let m = mRaw;
  let w = null;

  if (m && wcoRaw) {
    w = [m[0] - wcoRaw[0], m[1] - wcoRaw[1], m[2] - wcoRaw[2]];
  } else if (wRaw) {
    w = wRaw;
  }
  if (!m && w && wcoRaw) {
    m = [w[0] + wcoRaw[0], w[1] + wcoRaw[1], w[2] + wcoRaw[2]];
  }
  const prevWArray = (prevW.x !== null && prevW.y !== null && prevW.z !== null)
    ? [prevW.x, prevW.y, prevW.z]
    : null;
  if (!w && prevWArray) w = prevWArray;

  const displayWorkCmd = w || prevWArray || m;

  if (displayWorkCmd) {
    const workReal = [
      commandedDeltaToReal("x", displayWorkCmd[0]),
      commandedDeltaToReal("y", displayWorkCmd[1]),
      commandedDeltaToReal("z", displayWorkCmd[2]),
    ];
    lastWorkPosition = {
      x: Number(displayWorkCmd[0]),
      y: Number(displayWorkCmd[1]),
      z: Number(displayWorkCmd[2]),
    };
    readout.droMx.textContent = Number(workReal[0]).toFixed(3);
    readout.droMy.textContent = Number(workReal[1]).toFixed(3);
    readout.droMz.textContent = Number(workReal[2]).toFixed(3);
  }
  updateBoundsReadout();
  if (serial && Array.isArray(serial.responses)) {
    const hasError = serial.responses.some((line) => String(line).toLowerCase().startsWith("error"));
    if (hasError) {
      log("Serial error", serial);
    }
  }
}

async function refreshSerialStatusOnly() {
  const result = await api("/api/serial/status");
  renderSerialStatus(result.status);
  return result.status;
}

async function connectSerial() {
  if (!ui.serialPort.value && appConfig?.serial?.port) {
    ui.serialPort.value = appConfig.serial.port;
  }
  if (!ui.serialPort.value) {
    throw new Error("Select controller port first");
  }
  const result = await api("/api/serial/connect", {
    method: "POST",
    body: JSON.stringify({
      port: ui.serialPort.value,
      baudrate: Number(ui.serialBaudrate.value),
      dry_run: ui.serialDryRun.checked,
    }),
  });
  appConfig = result.config || appConfig;
  renderSerialStatus(result.status, result.serial);
  try {
    const query = await api("/api/serial/query", { method: "POST", body: "{}" });
    renderSerialStatus(query.status, query.serial);
    const machineState = String(query?.status?.position?.state || "").toLowerCase();
    if (machineState.startsWith("alarm")) {
      const unlocked = await api("/api/serial/unlock", { method: "POST", body: "{}" });
      renderSerialStatus(unlocked.status, unlocked.serial);
      const queriedAgain = await api("/api/serial/query", { method: "POST", body: "{}" });
      renderSerialStatus(queriedAgain.status, queriedAgain.serial);
      log("Controller unlocked from alarm state");
    }
  } catch (error) {
    log(`Connect follow-up failed: ${error.message || error}`);
  }
  startSerialPolling();
}

async function toggleMotionConnection() {
  const status = await refreshSerialStatusOnly();
  if (status.connected) {
    await postSerial("/api/serial/disconnect");
    stopSerialPolling();
    return;
  }
  await connectSerial();
}

async function postSerial(path) {
  const result = await api(path, { method: "POST", body: "{}" });
  renderSerialStatus(result.status, result.serial);
  if (path === "/api/serial/disconnect") {
    stopSerialPolling();
  }
  return result;
}

function startSerialPolling() {
  // Continuous polling is intentionally disabled.
  // We query status in short bursts only after motion commands.
}

function stopSerialPolling() {
  if (serialPollTimer) window.clearInterval(serialPollTimer);
  serialPollTimer = null;
  serialPollBusy = false;
  if (serialBurstTimer) window.clearTimeout(serialBurstTimer);
  serialBurstTimer = null;
  serialBurstRemaining = 0;
}

function requestStatusBurst(samples = 4, intervalMs = 200) {
  const count = Math.max(1, Math.floor(Number(samples) || 1));
  const interval = Math.max(80, Math.floor(Number(intervalMs) || 200));
  if (serialBurstTimer) {
    window.clearTimeout(serialBurstTimer);
    serialBurstTimer = null;
  }
  serialBurstRemaining = count;
  const tick = () => {
    if (serialBurstRemaining <= 0) {
      serialBurstTimer = null;
      return;
    }
    if (serialPollBusy) {
      serialBurstTimer = window.setTimeout(tick, interval);
      return;
    }
    serialPollBusy = true;
    api("/api/serial/query", { method: "POST", body: "{}" })
      .then((result) => renderSerialStatus(result.status))
      .catch(() => {})
      .finally(() => {
        serialPollBusy = false;
        serialBurstRemaining -= 1;
        if (serialBurstRemaining > 0) {
          serialBurstTimer = window.setTimeout(tick, interval);
        } else {
          serialBurstTimer = null;
        }
      });
  };
  void tick();
}

function shiftJogStep(direction) {
  const options = [...ui.jogStep.options];
  const current = options.findIndex((option) => option.value === ui.jogStep.value);
  const next = Math.max(0, Math.min(options.length - 1, current + direction));
  ui.jogStep.value = options[next].value;
  refreshMotionCalibrationReadout();
}

async function jogAxis(axis, sign) {
  const moveReal = Number(ui.jogStep.value) * sign;
  const commandedDelta = realDeltaToCommanded(axis.toLowerCase(), moveReal);
  const dx = axis.toLowerCase() === "x" ? commandedDelta : 0;
  const dy = axis.toLowerCase() === "y" ? commandedDelta : 0;
  const dz = axis.toLowerCase() === "z" ? commandedDelta : 0;
  assertRelativeMoveInBounds(dx, dy, dz, "Jog");
  const result = await api("/api/jog", {
    method: "POST",
    body: JSON.stringify({ axis, distance_mm: moveReal }),
  });
  ui.gcode.textContent = result.gcode.join("\n");
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(3, 180);
}

async function jogVector(dx, dy, dz = 0) {
  const step = Number(ui.jogStep.value);
  const dxCmd = realDeltaToCommanded("x", dx * step);
  const dyCmd = realDeltaToCommanded("y", dy * step);
  const dzCmd = realDeltaToCommanded("z", dz * step);
  assertRelativeMoveInBounds(dxCmd, dyCmd, dzCmd, "Jog");
  const result = await api("/api/jog/vector", {
    method: "POST",
    body: JSON.stringify({ dx_mm: dx * step, dy_mm: dy * step, dz_mm: dz * step }),
  });
  ui.gcode.textContent = result.gcode.join("\n");
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(3, 180);
}

async function holdAxisSegment(axis, sign) {
  const result = await api("/api/jog/hold-start", {
    method: "POST",
    body: JSON.stringify({ axis, direction: sign }),
  });
  ui.gcode.textContent = (result.gcode || []).join("\n");
  renderSerialStatus(result.status, result.serial);
}

async function holdVectorSegment(dx, dy, dz = 0) {
  const result = await api("/api/jog/hold-start-vector", {
    method: "POST",
    body: JSON.stringify({
      dx_sign: dx,
      dy_sign: dy,
      dz_sign: dz,
    }),
  });
  ui.gcode.textContent = (result.gcode || []).join("\n");
  renderSerialStatus(result.status, result.serial);
}

function bindRepeatPress(button, options) {
  const {
    tapAction,
    repeatAction,
    holdDelayMs = 260,
    holdIntervalMs = 180,
    actionName = "Moving",
    errorName = "Continuous move failed",
  } = options;
  let press = null;

  const release = () => {
    if (!press) return;
    const state = press;
    press = null;
    window.clearTimeout(state.holdTimer);
    if (state.repeatTimer) window.clearTimeout(state.repeatTimer);
    button.classList.remove("holding");
    if (!state.holding) {
      if (tapAction) task(actionName, tapAction);
      return;
    }
  };

  const beginRepeatLoop = () => {
    const tick = async () => {
      if (!press || !press.holding) return;
      if (press.busy) {
        press.repeatTimer = window.setTimeout(tick, holdIntervalMs);
        return;
      }
      press.busy = true;
      try {
        await repeatAction();
      } catch (error) {
        log(error.message || errorName);
        setStatus("Error");
        release();
        return;
      } finally {
        if (press) press.busy = false;
      }
      if (press?.holding) {
        press.repeatTimer = window.setTimeout(tick, holdIntervalMs);
      }
    };
    void tick();
  };

  const onPointerDown = (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    release();
    button.setPointerCapture?.(event.pointerId);
    press = {
      holding: false,
      busy: false,
      holdTimer: window.setTimeout(() => {
        if (!press) return;
        press.holding = true;
        button.classList.add("holding");
        setStatus("Jogging");
        beginRepeatLoop();
      }, holdDelayMs),
      repeatTimer: null,
    };
  };

  button.addEventListener("pointerdown", onPointerDown);
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("lostpointercapture", release);
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  activeHoldReleases.add(release);
}

function bindAxisHoldPress(button, axis, sign) {
  let press = null;

  const release = () => {
    if (!press) return;
    const state = press;
    press = null;
    window.clearTimeout(state.holdTimer);
    if (state.repeatTimer) window.clearTimeout(state.repeatTimer);
    button.classList.remove("holding");
    if (!state.holding) {
      task("Jogging", () => jogAxis(axis, sign));
      return;
    }
    void postSerial("/api/jog/hold-stop")
      .then(() => requestStatusBurst(4, 160))
      .catch((error) => log(error.message || "Stop jog failed"));
  };

  const beginLoop = () => {
    const tick = async () => {
      if (!press?.holding) return;
      if (press.busy) {
        press.repeatTimer = window.setTimeout(tick, 320);
        return;
      }
      press.busy = true;
      try {
        await holdAxisSegment(axis, sign);
      } catch (error) {
        log(error.message || "Continuous jog failed");
        release();
        return;
      } finally {
        if (press) press.busy = false;
      }
      if (press?.holding) {
        press.repeatTimer = window.setTimeout(tick, 320);
      }
    };
    void tick();
  };

  button.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    release();
    button.setPointerCapture?.(event.pointerId);
    press = {
      holding: false,
      busy: false,
      holdTimer: window.setTimeout(() => {
        if (!press) return;
        press.holding = true;
        button.classList.add("holding");
        beginLoop();
      }, 250),
      repeatTimer: null,
    };
  });
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("lostpointercapture", release);
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  activeHoldReleases.add(release);
}

function bindVectorHoldPress(button, dx, dy, dz = 0) {
  let press = null;

  const release = () => {
    if (!press) return;
    const state = press;
    press = null;
    window.clearTimeout(state.holdTimer);
    if (state.repeatTimer) window.clearTimeout(state.repeatTimer);
    button.classList.remove("holding");
    if (!state.holding) {
      task("Jogging", () => jogVector(dx, dy, dz));
      return;
    }
    void postSerial("/api/jog/hold-stop")
      .then(() => requestStatusBurst(4, 160))
      .catch((error) => log(error.message || "Stop diagonal jog failed"));
  };

  const beginLoop = () => {
    const tick = async () => {
      if (!press?.holding) return;
      if (press.busy) {
        press.repeatTimer = window.setTimeout(tick, 320);
        return;
      }
      press.busy = true;
      try {
        await holdVectorSegment(dx, dy, dz);
      } catch (error) {
        log(error.message || "Continuous diagonal jog failed");
        release();
        return;
      } finally {
        if (press) press.busy = false;
      }
      if (press?.holding) {
        press.repeatTimer = window.setTimeout(tick, 320);
      }
    };
    void tick();
  };

  button.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    release();
    button.setPointerCapture?.(event.pointerId);
    press = {
      holding: false,
      busy: false,
      holdTimer: window.setTimeout(() => {
        if (!press) return;
        press.holding = true;
        button.classList.add("holding");
        beginLoop();
      }, 250),
      repeatTimer: null,
    };
  });
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("lostpointercapture", release);
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  activeHoldReleases.add(release);
}

async function goZero(target) {
  if (target === "xy") {
    assertAbsoluteMoveInBounds({ x: 0, y: 0 }, "Go X0Y0");
  } else if (target === "z") {
    assertAbsoluteMoveInBounds({ z: 0 }, "Go Z0");
  } else {
    assertAbsoluteMoveInBounds({ x: 0, y: 0, z: 0 }, "Go zero");
  }
  const result = await api("/api/motion/go-zero", {
    method: "POST",
    body: JSON.stringify({ target }),
  });
  ui.gcode.textContent = result.gcode.join("\n");
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(5, 180);
}

function currentWorkXY() {
  const pos = currentWorkXYZ();
  return [pos.x ?? 0, pos.y ?? 0];
}

function motionMapRange(axis, currentCmd) {
  const limitsCmd = axisLimits(axis);
  const limitsReal = commandedRangeToReal(axis, limitsCmd);
  const current = currentCmd === null || currentCmd === undefined ? null : commandedDeltaToReal(axis, currentCmd);
  let min = limitsReal.min;
  let max = limitsReal.max;
  const fallbackSpan = 200;
  if (min === null && max === null) {
    const base = current ?? 0;
    min = base - fallbackSpan / 2;
    max = base + fallbackSpan / 2;
  } else if (min === null) {
    min = max - fallbackSpan;
  } else if (max === null) {
    max = min + fallbackSpan;
  }
  if (max <= min) {
    max = min + 1;
  }
  if (max - min > 8000) {
    const base = current ?? (min + max) / 2;
    min = base - 200;
    max = base + 200;
  }
  return { min, max };
}

function drawMotionMap() {
  if (!ui.motionMap) return;
  const ctx = ui.motionMap.getContext("2d");
  const width = ui.motionMap.width;
  const height = ui.motionMap.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#e3e8ef";
  ctx.lineWidth = 1;
  for (let i = 1; i < 10; i += 1) {
    const x = (width * i) / 10;
    const y = (height * i) / 10;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  const posCmd = currentWorkXYZ();
  const pos = {
    x: posCmd.x === null ? null : commandedDeltaToReal("x", posCmd.x),
    y: posCmd.y === null ? null : commandedDeltaToReal("y", posCmd.y),
  };
  const xRange = motionMapRange("x", posCmd.x);
  const yRange = motionMapRange("y", posCmd.y);
  const xSpan = xRange.max - xRange.min;
  const ySpan = yRange.max - yRange.min;
  const px = (x) => ((x - xRange.min) / xSpan) * width;
  const py = (y) => height - ((y - yRange.min) / ySpan) * height;

  const xLimits = commandedRangeToReal("x", axisLimits("x"));
  const yLimits = commandedRangeToReal("y", axisLimits("y"));
  if (xLimits.min !== null && yLimits.min !== null && xLimits.max !== null && yLimits.max !== null) {
    ctx.strokeStyle = "#1f7a68";
    ctx.lineWidth = 2;
    ctx.strokeRect(
      px(xLimits.min),
      py(yLimits.max),
      px(xLimits.max) - px(xLimits.min),
      py(yLimits.min) - py(yLimits.max),
    );
  } else {
    ctx.strokeStyle = "#1f7a68";
    ctx.lineWidth = 2;
    if (xLimits.min !== null) {
      const x = px(xLimits.min);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    if (xLimits.max !== null) {
      const x = px(xLimits.max);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    if (yLimits.min !== null) {
      const y = py(yLimits.min);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    if (yLimits.max !== null) {
      const y = py(yLimits.max);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
  }

  if (0 >= xRange.min && 0 <= xRange.max) {
    ctx.strokeStyle = "#b9c3cf";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(px(0), 0);
    ctx.lineTo(px(0), height);
    ctx.stroke();
  }
  if (0 >= yRange.min && 0 <= yRange.max) {
    ctx.strokeStyle = "#b9c3cf";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(0, py(0));
    ctx.lineTo(width, py(0));
    ctx.stroke();
  }

  if (pos.x !== null && pos.y !== null) {
    ctx.fillStyle = "#1656a0";
    ctx.beginPath();
    ctx.arc(px(pos.x), py(pos.y), 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#233244";
    ctx.font = "12px Inter, sans-serif";
    const xReal = commandedDeltaToReal("x", pos.x);
    const yReal = commandedDeltaToReal("y", pos.y);
    ctx.fillText(`X ${xReal.toFixed(1)}  Y ${yReal.toFixed(1)}`, 8, height - 8);
  }
}

function updateBoundsReadout() {
  const captured = runtimeBounds?.captured || boundsCapture;
  const effectiveCmd = runtimeBounds?.effective || null;
  const effectiveReal = {
    x: commandedRangeToReal("x", effectiveCmd?.x),
    y: commandedRangeToReal("y", effectiveCmd?.y),
  };
  const capturedReal = {
    origin: Array.isArray(captured?.origin)
      ? [commandedDeltaToReal("x", captured.origin[0]), commandedDeltaToReal("y", captured.origin[1])]
      : null,
    xMax: Array.isArray(captured?.xMax)
      ? [commandedDeltaToReal("x", captured.xMax[0]), commandedDeltaToReal("y", captured.xMax[1])]
      : null,
    yMax: Array.isArray(captured?.yMax)
      ? [commandedDeltaToReal("x", captured.yMax[0]), commandedDeltaToReal("y", captured.yMax[1])]
      : null,
  };
  const enabled = workspaceBoundsEnabled();
  const fmtNum = (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "null");
  const fmtMachine = (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "-");
  const fmtRange = (range) => {
    const min = numOrNull(range?.min);
    const max = numOrNull(range?.max);
    if (min === null || max === null) return "null";
    return `[${min.toFixed(3)}, ${max.toFixed(3)}]`;
  };
  const fmtPoint = (point) => (
    Array.isArray(point) && point.length >= 2
      ? `[${fmtNum(point[0])}, ${fmtNum(point[1])}]`
      : "null"
  );

  readout.droWx.textContent = fmtRange(effectiveReal?.x);
  readout.droWy.textContent = fmtRange(effectiveReal?.y);
  readout.droWz.textContent = "null";

  const lines = [
    `Boundary Enabled: ${enabled ? "true" : "false"}`,
    "",
    "Axis | Work Real | Boundary Real",
    `X    | ${fmtMachine(readout.droMx.textContent)} | ${fmtRange(effectiveReal?.x)}`,
    `Y    | ${fmtMachine(readout.droMy.textContent)} | ${fmtRange(effectiveReal?.y)}`,
    `Z    | ${fmtMachine(readout.droMz.textContent)} | null`,
    "",
    `Captured Origin: ${fmtPoint(capturedReal.origin)}`,
    `Captured X Max:  ${fmtPoint(capturedReal.xMax)}`,
    `Captured Y Max:  ${fmtPoint(capturedReal.yMax)}`,
  ];
  if (readout.bounds) readout.bounds.textContent = lines.join("\n");
  setEnableBoundsButtonText();
  drawMotionMap();
}

async function refreshRuntimeBounds() {
  const result = await api("/api/motion/bounds");
  runtimeBounds = result.bounds || null;
  boundsCapture = cloneBoundsCaptured(runtimeBounds?.captured);
  updateBoundsReadout();
}

async function captureBoundsPoint(name) {
  if (name === "origin") {
    const zeroResult = await api("/api/motion/set-work-zero", {
      method: "POST",
      body: JSON.stringify({ target: "xy" }),
    });
    ui.gcode.textContent = (zeroResult.gcode || []).join("\n");
    renderSerialStatus(zeroResult.status, zeroResult.serial);
    try {
      const queried = await api("/api/serial/query", { method: "POST", body: "{}" });
      renderSerialStatus(queried.status, queried.serial);
    } catch {
      // Keep going even if query fails.
    }
    const result = await api("/api/motion/bounds/capture", {
      method: "POST",
      body: JSON.stringify({ point: "origin", x: 0.0, y: 0.0 }),
    });
    runtimeBounds = result.bounds || null;
    boundsCapture = cloneBoundsCaptured(runtimeBounds?.captured);
    updateBoundsReadout();
    log("Bounds set: origin (X0Y0)", { x_real_mm: 0.0, y_real_mm: 0.0 });
    return;
  }

  const statusResult = await api("/api/serial/query", { method: "POST", body: "{}" });
  renderSerialStatus(statusResult.status, statusResult.serial);
  const pos = statusResult?.status?.position || {};
  let wx = null;
  let wy = null;
  if (Array.isArray(pos.wpos) && pos.wpos.length >= 2) {
    wx = Number(pos.wpos[0]);
    wy = Number(pos.wpos[1]);
  } else if (
    Array.isArray(pos.mpos) && pos.mpos.length >= 2
    && Array.isArray(pos.wco) && pos.wco.length >= 2
  ) {
    wx = Number(pos.mpos[0]) - Number(pos.wco[0]);
    wy = Number(pos.mpos[1]) - Number(pos.wco[1]);
  }
  if (wx === null || wy === null || !Number.isFinite(Number(wx)) || !Number.isFinite(Number(wy))) {
    throw new Error("Cannot read live XY from controller. Click Status ? and retry.");
  }
  const x = Number(wx);
  const y = Number(wy);
  const result = await api("/api/motion/bounds/capture", {
    method: "POST",
    body: JSON.stringify({ point: name, x, y }),
  });
  runtimeBounds = result.bounds || null;
  boundsCapture = cloneBoundsCaptured(runtimeBounds?.captured);
  updateBoundsReadout();
  log(`Bounds set: ${name}`, {
    x_real_mm: commandedDeltaToReal("x", x),
    y_real_mm: commandedDeltaToReal("y", y),
  });
}

async function applyBounds() {
  const captured = runtimeBounds?.captured || boundsCapture;
  const effective = runtimeBounds?.effective || null;
  if (workspaceBoundsEnabled()) {
    await api("/api/motion/bounds/enable", {
      method: "POST",
      body: JSON.stringify({ enabled: false }),
    });
    await refreshRuntimeBounds();
    await persistWorkspaceBoundsToConfig(false);
    updateBoundsReadout();
    log("Workspace bounds disabled");
    return;
  }

  if (!captured.origin || !captured.xMax || !captured.yMax) {
    throw new Error("Set X0Y0, X Max, and Y Max first");
  }
  const xMin = effective?.x?.min;
  const xMax = effective?.x?.max;
  const yMin = effective?.y?.min;
  const yMax = effective?.y?.max;
  if (![xMin, xMax, yMin, yMax].every((value) => Number.isFinite(value))) {
    throw new Error("Bounds not complete yet. Set X0Y0, X Max, and Y Max again.");
  }
  const width = Number(xMax) - Number(xMin);
  const height = Number(yMax) - Number(yMin);
  if (width < 1 || height < 1) {
    throw new Error("Bounds too small. Please set X Max and Y Max farther from X0Y0.");
  }
  await api("/api/motion/bounds/apply", { method: "POST", body: "{}" });
  await refreshRuntimeBounds();
  await persistWorkspaceBoundsToConfig(true);
  updateBoundsReadout();
  log("Workspace bounds enabled", { xMin, xMax, yMin, yMax });
}

async function clearBounds() {
  const result = await api("/api/motion/bounds/clear", { method: "POST", body: "{}" });
  runtimeBounds = result.bounds || null;
  boundsCapture = cloneBoundsCaptured(runtimeBounds?.captured);
  await persistWorkspaceBoundsToConfig(false, true);
  updateBoundsReadout();
  setStatus("Bounds cleared");
  log("Workspace bounds cleared");
}

async function persistWorkspaceBoundsToConfig(enabled, clearAll = false) {
  if (!appConfig?.machine) return;
  if (!appConfig.machine.workspace_bounds || typeof appConfig.machine.workspace_bounds !== "object") {
    appConfig.machine.workspace_bounds = {};
  }
  const captured = runtimeBounds?.captured || {};
  const effective = runtimeBounds?.effective || {};
  appConfig.machine.workspace_bounds.enabled = Boolean(enabled);
  if (clearAll) {
    appConfig.machine.workspace_bounds.origin = null;
    appConfig.machine.workspace_bounds.xMax = null;
    appConfig.machine.workspace_bounds.yMax = null;
    appConfig.machine.workspace_bounds.x = null;
    appConfig.machine.workspace_bounds.y = null;
  } else {
    appConfig.machine.workspace_bounds.origin = captured.origin || null;
    appConfig.machine.workspace_bounds.xMax = captured.xMax || null;
    appConfig.machine.workspace_bounds.yMax = captured.yMax || null;
    appConfig.machine.workspace_bounds.x = effective.x || null;
    appConfig.machine.workspace_bounds.y = effective.y || null;
  }
  const saved = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = saved.config || appConfig;
}

async function runPaperFeed(lengthMm = null, repeat = 1) {
  const parsedLength = Number.isFinite(Number(lengthMm)) && Number(lengthMm) > 0
    ? Number(lengthMm)
    : Number(ui.rollerLength.value);
  const safeRepeat = Number.isFinite(Number(repeat)) ? Math.max(1, Math.min(500, Number(repeat))) : 1;
  const result = await api("/api/paper-feed/run", {
    method: "POST",
    body: JSON.stringify({
      direction: "forward",
      length_mm: parsedLength,
      repeat: safeRepeat,
    }),
  });
  renderSerialStatus(result.status, result.serial);
  requestStatusBurst(3, 160);
}

async function savePaperFeedSetting() {
  const feedLen = Number(ui.rollerLength.value);
  if (!Number.isFinite(feedLen) || feedLen <= 0) {
    throw new Error("Paper feed step length must be > 0");
  }
  appConfig.paper_feed.feed_length_mm = feedLen;
  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = result.config;
  ui.rollerLength.value = appConfig.paper_feed?.feed_length_mm || feedLen;
  setStatus("Feed setting saved");
  log("Paper feed step saved", { feed_length_mm: ui.rollerLength.value });
}

function applyMeasuredScaleForAxis(axis, measuredDistanceMm, jogStepMm) {
  const cfgAxis = appConfig?.machine?.axes?.[axis];
  if (!cfgAxis) return null;
  if (!Number.isFinite(jogStepMm) || jogStepMm <= 0) {
    throw new Error("Jog step must be > 0");
  }
  if (!Number.isFinite(measuredDistanceMm) || measuredDistanceMm <= 0) {
    throw new Error(`${axis.toUpperCase()} measured distance must be > 0`);
  }
  const inputMap = {
    x: ui.axisXScale,
    y: ui.axisYScale,
    z: ui.axisZScale,
  };
  const current = Number(inputMap[axis]?.value ?? cfgAxis.actual_mm_per_commanded_mm);
  if (!Number.isFinite(current) || Math.abs(current) < 1e-9) {
    throw new Error(`${axis.toUpperCase()} calibration ratio is invalid`);
  }
  const next = current * (measuredDistanceMm / jogStepMm);
  return Number(next.toFixed(6));
}

function applyMeasuredMotionScales() {
  const jogStepMm = Number(ui.jogStep.value);
  const updates = {};
  const xMeasured = Number(ui.axisXMeasured.value);
  const yMeasured = Number(ui.axisYMeasured.value);
  const zMeasured = Number(ui.axisZMeasured.value);

  if (Number.isFinite(xMeasured) && xMeasured > 0) {
    updates.x = applyMeasuredScaleForAxis("x", xMeasured, jogStepMm);
    ui.axisXScale.value = Number(updates.x).toFixed(6);
  }
  if (Number.isFinite(yMeasured) && yMeasured > 0) {
    updates.y = applyMeasuredScaleForAxis("y", yMeasured, jogStepMm);
    ui.axisYScale.value = Number(updates.y).toFixed(6);
  }
  if (Number.isFinite(zMeasured) && zMeasured > 0) {
    updates.z = applyMeasuredScaleForAxis("z", zMeasured, jogStepMm);
    ui.axisZScale.value = Number(updates.z).toFixed(6);
  }
  if (!Object.keys(updates).length) {
    throw new Error("Enter at least one measured distance (X/Y/Z) first");
  }

  refreshMotionCalibrationReadout();
  log("Measured motion scale applied (not saved yet)", updates);
}

async function saveMotionScaleSetting() {
  const x = Number(ui.axisXScale.value);
  const y = Number(ui.axisYScale.value);
  const z = Number(ui.axisZScale.value);
  if (!Number.isFinite(x) || x <= 0) throw new Error("X calibration ratio must be > 0");
  if (!Number.isFinite(y) || y <= 0) throw new Error("Y calibration ratio must be > 0");
  if (!Number.isFinite(z) || z <= 0) throw new Error("Z calibration ratio must be > 0");

  appConfig.machine.axes.x.actual_mm_per_commanded_mm = Number(x.toFixed(6));
  appConfig.machine.axes.y.actual_mm_per_commanded_mm = Number(y.toFixed(6));
  appConfig.machine.axes.z.actual_mm_per_commanded_mm = Number(z.toFixed(6));

  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = result.config || appConfig;
  hydrateMotionCalibrationInputs();
  updateBoundsReadout();
  setStatus("Motion calibration saved");
  log("Motion calibration saved", {
    x_actual_mm_per_commanded_mm: appConfig.machine.axes.x.actual_mm_per_commanded_mm,
    y_actual_mm_per_commanded_mm: appConfig.machine.axes.y.actual_mm_per_commanded_mm,
    z_actual_mm_per_commanded_mm: appConfig.machine.axes.z.actual_mm_per_commanded_mm,
  });
}

async function loadFirmwareSettings() {
  const result = await api("/api/firmware/settings");
  const configured = result.configured || {};
  ui.flashHex.value = configured.hex_path || "firmware/grbl3axis.hex";
  const ports = result.ports || [];
  if (ports.length) {
    fillSelect(ui.flashPort, ports.map((port) => ({ value: port.device, label: port.device })));
  }
  if (ui.flashLog) ui.flashLog.textContent = "Firmware settings loaded";
  log("Firmware settings loaded", configured);
}

async function flashFirmware() {
  const result = await api("/api/firmware/flash", {
    method: "POST",
    body: JSON.stringify({
      port: ui.flashPort.value,
      board: "uno_atmega328p",
      mcu: "atmega328p",
      baudrate: 115200,
      programmer: "arduino",
      hex_path: ui.flashHex.value,
    }),
  });
  if (ui.flashLog) ui.flashLog.textContent = JSON.stringify(result.flash || result, null, 2);
  log("Firmware flash result", result.flash || result);
}

function commitSelectedPixelToActiveCalibrationPoint(autoAdvance = false) {
  if (!selectedPixel || !appConfig?.calibration?.points?.length) return false;
  const index = Number(ui.activeCalPoint.value || 0);
  appConfig.calibration.points[index].pixel = [selectedPixel[0], selectedPixel[1]];
  readout.clicked.textContent = fmtPoint(selectedPixel);
  if (autoAdvance) {
    const count = appConfig.calibration.points.length;
    ui.activeCalPoint.value = String((index + 1) % count);
  }
  return true;
}

function nextCalPoint() {
  const nextIndex = nextCalibrationIndexClockwise(ui.activeCalPoint.value);
  ui.activeCalPoint.value = String(nextIndex);
  drawOverlay();
}

async function saveCalibration() {
  await saveCameraSetup(true);
  renderCalibration();
  drawOverlay();
}

async function clearCalibration() {
  const width = Number(appConfig?.camera?.width_px || ui.cameraWidth.value || 1280);
  const height = Number(appConfig?.camera?.height_px || ui.cameraHeight.value || 720);
  const realPoints = (appConfig?.calibration?.points || []).map((point) => point.real_mm);
  const fallbackReal = [[0, 0], [width, 0], [width, height], [0, height]];
  const pixels = [[0, 0], [width, 0], [width, height], [0, height]];
  appConfig.calibration.points = paperRoiLabels.map((label, index) => ({
    label: appConfig.calibration.points?.[index]?.label || label.replace("region", "mark"),
    pixel: pixels[index],
    real_mm: realPoints[index] || fallbackReal[index],
  }));
  await saveCameraSetup(true);
  renderCalibration();
  drawOverlay();
  setStatus("Calibration cleared");
}

function useSelectedPixelForPaperRoi() {
  if (!selectedPixel) {
    log("Click a camera point first");
    return;
  }
  const points = ensurePaperRoiPoints();
  const index = activeStampRegionCornerIndex();
  points[index] = [selectedPixel[0], selectedPixel[1]];
  renderPaperRoi();
  drawOverlay();
}

function commitPointToActiveStampRegion(point) {
  if (!Array.isArray(point)) return false;
  ensurePaperRoiPoints();
  const index = activeStampRegionCornerIndex();
  appConfig.vision.paper_roi_points[index] = [point[0], point[1]];
  selectedPixel = point;
  showStampRegionOverlay = true;
  const button = $("#toggleStampRegionOverlayBtn");
  if (button) button.textContent = "Disable";
  renderPaperRoi();
  setStatus(`Region corner ${index + 1} updated`);
  return true;
}

function moveStampRegionPoint(index, point) {
  if (!Array.isArray(point)) return false;
  ensurePaperRoiPoints();
  const points = appConfig.vision.paper_roi_points;
  const existing = points.slice(0, 4);
  if (existing.every((item) => Array.isArray(item) && item.length === 2)) {
    const xs = existing.map((item) => Number(item[0]));
    const ys = existing.map((item) => Number(item[1]));
    let left = Math.min(...xs);
    let right = Math.max(...xs);
    let top = Math.min(...ys);
    let bottom = Math.max(...ys);
    if (index === 0 || index === 3) left = Number(point[0]);
    if (index === 1 || index === 2) right = Number(point[0]);
    if (index === 0 || index === 1) top = Number(point[1]);
    if (index === 2 || index === 3) bottom = Number(point[1]);
    const minSize = 8;
    if (right - left < minSize) {
      if (index === 0 || index === 3) left = right - minSize;
      else right = left + minSize;
    }
    if (bottom - top < minSize) {
      if (index === 0 || index === 1) top = bottom - minSize;
      else bottom = top + minSize;
    }
    points[0] = [left, top];
    points[1] = [right, top];
    points[2] = [right, bottom];
    points[3] = [left, bottom];
  } else {
    points[index] = [point[0], point[1]];
  }
  selectedPixel = point;
  syncStampRegionCornerSelects(index);
  renderPaperRoi();
  return true;
}

function moveStampRegionEdge(edgeIndex, delta) {
  ensurePaperRoiPoints();
  const points = appConfig.vision.paper_roi_points;
  if (points.slice(0, 4).some((point) => !Array.isArray(point))) return;
  const xs = points.slice(0, 4).map((point) => Number(point[0]));
  const ys = points.slice(0, 4).map((point) => Number(point[1]));
  let left = Math.min(...xs);
  let right = Math.max(...xs);
  let top = Math.min(...ys);
  let bottom = Math.max(...ys);
  if (edgeIndex === 0) top += delta[1];
  if (edgeIndex === 1) right += delta[0];
  if (edgeIndex === 2) bottom += delta[1];
  if (edgeIndex === 3) left += delta[0];
  const minSize = 8;
  if (right - left < minSize) {
    if (edgeIndex === 1) right = left + minSize;
    if (edgeIndex === 3) left = right - minSize;
  }
  if (bottom - top < minSize) {
    if (edgeIndex === 2) bottom = top + minSize;
    if (edgeIndex === 0) top = bottom - minSize;
  }
  points[0] = [left, top];
  points[1] = [right, top];
  points[2] = [right, bottom];
  points[3] = [left, bottom];
  renderPaperRoi();
  drawOverlay();
}

async function setCurrentMachineForPaperRoi() {
  ensurePaperRoiPoints();
  const statusResult = await api("/api/serial/query", { method: "POST", body: "{}" });
  renderSerialStatus(statusResult.status, statusResult.serial);
  const pos = currentWorkXYZ();
  if (pos.x === null || pos.y === null) {
    throw new Error("Cannot read current machine XY from controller");
  }
  const index = activeStampRegionCornerIndex();
  appConfig.vision.stamp_region_machine_points[index] = [Number(pos.x), Number(pos.y)];
  renderPaperRoi();
  drawOverlay();
  log("Stamp/detect region machine corner set", {
    corner: paperRoiLabels[index],
    commanded_xy: appConfig.vision.stamp_region_machine_points[index],
  });
}

function nextPaperRoiPoint() {
  const current = activeStampRegionCornerIndex();
  syncStampRegionCornerSelects((current + 1) % 4);
}

function nextStampRegionBoundPoint() {
  nextPaperRoiPoint();
}

async function clearStampRegionMachinePoints() {
  ensurePaperRoiPoints();
  appConfig.vision.stamp_region_machine_points = [];
  appConfig.vision.stamp_region_real_mm = [];
  appConfig.vision.stamp_region_commanded_mm = [];
  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = result.config || appConfig;
  renderPaperRoi();
  setStatus("Stamp region machine corners cleared");
  log("Stamp region machine corners cleared");
}

async function savePaperRoi() {
  if (!paperRoiComplete()) {
    throw new Error("Set all four stamp/detect region corners first");
  }
  const orderedEntries = orderQuadEntries(appConfig.vision.paper_roi_points.slice(0, 4));
  if (!orderedEntries) {
    throw new Error("Stamp/detect region pixels are invalid");
  }
  const machinePoints = appConfig.vision.stamp_region_machine_points || [];
  const orderedPixels = orderedEntries.map((entry) => entry.point);
  const orderedMachine = orderedEntries.map((entry) => machinePoints[entry.index] || null);
  appConfig.vision.paper_roi_points = orderedPixels;
  appConfig.vision.stamp_region_machine_points = orderedMachine;
  const machineComplete = orderedMachine.every((point) => (
    Array.isArray(point)
    && point.length === 2
    && Number.isFinite(Number(point[0]))
    && Number.isFinite(Number(point[1]))
  ));
  if (machineComplete) {
    appConfig.vision.stamp_region_commanded_mm = orderedMachine.map((point) => [Number(point[0]), Number(point[1])]);
    appConfig.vision.stamp_region_real_mm = orderedMachine.map((point) => [
      commandedDeltaToReal("x", Number(point[0])),
      commandedDeltaToReal("y", Number(point[1])),
    ]);
  } else {
    appConfig.vision.stamp_region_commanded_mm = [];
    appConfig.vision.stamp_region_real_mm = [];
  }
  try {
    if (!machineComplete) {
      const resolved = [];
      for (const point of orderedPixels) {
        const preview = await api("/api/preview", {
          method: "POST",
          body: JSON.stringify({ source: "pixel", x: point[0], y: point[1], offset_mm: [0, 0] }),
        });
        resolved.push(preview.target);
      }
      appConfig.vision.stamp_region_real_mm = resolved.map((target) => target.real_xy_mm);
      appConfig.vision.stamp_region_commanded_mm = resolved.map((target) => target.commanded_xy_mm);
    }
  } catch (error) {
    if (!machineComplete) {
      appConfig.vision.stamp_region_real_mm = [];
      appConfig.vision.stamp_region_commanded_mm = [];
      log(`Region saved without machine-coordinate mapping: ${error.message || error}`);
    }
  }
  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = result.config || appConfig;
  renderPaperRoi();
  drawOverlay();
  setStatus("Stamp/detect region saved");
  log("Stamp/detect region saved", {
    pixel_points: appConfig.vision.paper_roi_points,
    machine_points: appConfig.vision.stamp_region_machine_points || [],
    real_mm: appConfig.vision.stamp_region_real_mm || [],
    commanded_mm: appConfig.vision.stamp_region_commanded_mm || [],
  });
}

async function clearPaperRoi() {
  if (!appConfig.vision || typeof appConfig.vision !== "object") appConfig.vision = {};
  appConfig.vision.paper_roi_points = [];
  appConfig.vision.stamp_region_machine_points = [];
  appConfig.vision.stamp_region_real_mm = [];
  appConfig.vision.stamp_region_commanded_mm = [];
  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify({ config: appConfig }),
  });
  appConfig = result.config || appConfig;
  renderPaperRoi();
  drawOverlay();
  setStatus("Stamp/detect region cleared");
  log("Stamp/detect region cleared");
}

function bindEvents() {
  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      activateTab(button.dataset.tab);
    });
  });

  ui.overlay.addEventListener("pointerdown", (event) => {
    if (!activeCameraEditPanel() || cameraMode === "document") return;
    if (cameraEditTarget === "region") {
      const nearestRegion = findNearestStampRegionPointIndex(event, 22);
      if (nearestRegion !== null) {
        draggingStampRegionPointIndex = nearestRegion;
        draggingStampRegionPointerId = event.pointerId;
        movedWhileDraggingStampRegion = false;
        syncStampRegionCornerSelects(nearestRegion);
        ui.overlay.style.cursor = "grabbing";
        ui.overlay.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        return;
      }
      const nearestEdge = findNearestStampRegionEdgeIndex(event, 12);
      if (nearestEdge !== null) {
        draggingStampRegionEdgeIndex = nearestEdge;
        draggingStampRegionEdgePointerId = event.pointerId;
        draggingStampRegionLastPoint = pointFromEvent(event);
        movedWhileDraggingStampRegion = false;
        ui.overlay.style.cursor = "grabbing";
        ui.overlay.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        return;
      }
      return;
    }
    if (cameraEditTarget !== "calibration") return;
    const nearest = findNearestCalibrationPointIndex(event, 22);
    if (nearest === null) return;
    draggingCalPointIndex = nearest;
    draggingCalPointerId = event.pointerId;
    movedWhileDraggingCal = false;
    ui.activeCalPoint.value = String(nearest);
    ui.overlay.style.cursor = "grabbing";
    ui.overlay.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });

  ui.overlay.addEventListener("pointermove", (event) => {
    if (draggingStampRegionEdgeIndex !== null && draggingStampRegionEdgePointerId === event.pointerId) {
      const point = pointFromEvent(event);
      if (!point || !draggingStampRegionLastPoint) return;
      const delta = [point[0] - draggingStampRegionLastPoint[0], point[1] - draggingStampRegionLastPoint[1]];
      draggingStampRegionLastPoint = point;
      movedWhileDraggingStampRegion = true;
      moveStampRegionEdge(draggingStampRegionEdgeIndex, delta);
      return;
    }

    if (draggingStampRegionPointIndex !== null && draggingStampRegionPointerId === event.pointerId) {
      const rect = ui.overlay.getBoundingClientRect();
      const overlayPoint = [event.clientX - rect.left, event.clientY - rect.top];
      const point = overlayToMediaClamped(overlayPoint);
      if (!point) return;
      movedWhileDraggingStampRegion = true;
      moveStampRegionPoint(draggingStampRegionPointIndex, point);
      drawOverlay();
      return;
    }

    if (draggingCalPointIndex === null || draggingCalPointerId !== event.pointerId) return;
    const rect = ui.overlay.getBoundingClientRect();
    const overlayPoint = [event.clientX - rect.left, event.clientY - rect.top];
    const point = overlayToMediaClamped(overlayPoint);
    if (!point) return;
    movedWhileDraggingCal = true;
    selectedPixel = point;
    appConfig.calibration.points[draggingCalPointIndex].pixel = [point[0], point[1]];
    readout.clicked.textContent = fmtPoint(point);
    renderCalibration();
    drawOverlay();
  });

  const finishCalDrag = (event) => {
    if (draggingStampRegionEdgeIndex !== null) {
      if (event?.pointerId !== undefined && draggingStampRegionEdgePointerId !== event.pointerId) return;
      const moved = movedWhileDraggingStampRegion;
      draggingStampRegionEdgeIndex = null;
      draggingStampRegionEdgePointerId = null;
      draggingStampRegionLastPoint = null;
      movedWhileDraggingStampRegion = false;
      ui.overlay.style.cursor = "";
      if (moved) {
        suppressNextOverlayClick = true;
        setStatus("Region edge moved");
        renderPaperRoi();
      }
      return;
    }

    if (draggingStampRegionPointIndex !== null) {
      if (event?.pointerId !== undefined && draggingStampRegionPointerId !== event.pointerId) return;
      const moved = movedWhileDraggingStampRegion;
      draggingStampRegionPointIndex = null;
      draggingStampRegionPointerId = null;
      movedWhileDraggingStampRegion = false;
      ui.overlay.style.cursor = "";
      if (moved) {
        suppressNextOverlayClick = true;
        setStatus("Region corner moved");
        renderPaperRoi();
      }
      return;
    }

    if (draggingCalPointIndex === null) return;
    if (event?.pointerId !== undefined && draggingCalPointerId !== event.pointerId) return;
    const moved = movedWhileDraggingCal;
    draggingCalPointIndex = null;
    draggingCalPointerId = null;
    movedWhileDraggingCal = false;
    ui.overlay.style.cursor = "";
    if (moved) {
      suppressNextOverlayClick = true;
      setStatus("Anchor moved");
      renderCalibration();
    }
  };

  ui.overlay.addEventListener("pointerup", finishCalDrag);
  ui.overlay.addEventListener("pointercancel", finishCalDrag);
  ui.overlay.addEventListener("lostpointercapture", finishCalDrag);

  ui.overlay.addEventListener("click", (event) => {
    if (suppressNextOverlayClick) {
      suppressNextOverlayClick = false;
      return;
    }
    const point = pointFromEvent(event);
    if (!point) {
      log("Click inside the camera/image area (not the gray margin).");
      return;
    }
    if (cameraMode === "document") {
      documentPixel = point;
    } else {
      selectedPixel = point;
      readout.clicked.textContent = fmtPoint(point);
      if (activeCameraEditPanel() && cameraEditTarget === "region" && commitPointToActiveStampRegion(point)) {
        // Region clicks are committed directly to the active red-box corner.
      } else if (activeCameraEditPanel() && cameraEditTarget === "calibration" && commitSelectedPixelToActiveCalibrationPoint(false)) {
        setStatus("Anchor updated");
        renderCalibration();
      }
    }
    drawOverlay();
  });
  ui.video.addEventListener("loadedmetadata", syncOverlaySize);
  ui.image.addEventListener("load", () => {
    syncOverlaySize();
    drawOverlay();
  });
  window.addEventListener("resize", syncOverlaySize);

  ui.workflowMode.addEventListener("change", updateModeUI);
  ui.cameraSource.addEventListener("change", updateCameraSourceFields);
  ui.crosshair.addEventListener("change", drawOverlay);
  ui.activeCalPoint.addEventListener("change", () => {
    cameraEditTarget = "calibration";
    drawOverlay();
  });
  ui.clearConsoleBtn?.addEventListener("click", clearConsole);

  $("#cameraToggleBtn").addEventListener("click", () => task("Camera", toggleCamera));
  $("#cameraToggleTopBtn").addEventListener("click", () => task("Camera", toggleCamera));
  ui.cameraSimulationBtn?.addEventListener("click", () => toggleCameraSimulationPicker());
  ui.cameraSimulationTopBtn?.addEventListener("click", () => toggleCameraSimulationPicker());
  ui.cameraSimulationFile?.addEventListener("change", () => {
    const file = ui.cameraSimulationFile.files?.[0] || null;
    if (!file) return;
    task("Camera simulation", () => startCameraSimulationFromFile(file));
    ui.cameraSimulationFile.value = "";
  });
  ui.rotateSimulationLeftBtn?.addEventListener("click", () => task("Rotate simulation", () => rotateSimulationPreview(false)));
  ui.rotateSimulationRightBtn?.addEventListener("click", () => task("Rotate simulation", () => rotateSimulationPreview(true)));
  ui.confirmSimulationBtn?.addEventListener("click", () => task("Confirm simulation", confirmCameraSimulation));
  ui.cancelSimulationPreviewBtn?.addEventListener("click", () => cancelCameraSimulationPreview());
  $("#cameraSettingsBtn").addEventListener("click", () => ui.cameraSettings.classList.toggle("hidden"));
  $("#refreshCameraDevicesBtn").addEventListener("click", () => task("Refreshing cameras", refreshCameraDevices));
  $("#saveCameraSetupBtn").addEventListener("click", () => task("Saving camera", () => saveCameraSetup(false)));
  $("#clearTargetBtn").addEventListener("click", clearTarget);

  ui.documentFile.addEventListener("change", () => {
    if (!ui.documentFile.files?.[0]) return;
    task("Loading document", uploadDocument);
  });
  $("#confirmModeABtn").addEventListener("click", () => task("Confirming Mode A", confirmModeA));
  $("#modeARunBtn").addEventListener("click", () => task("Running Mode A", runModeACycleOnce));
  $("#confirmModeBBtn").addEventListener("click", () => task("Confirming Mode B", confirmModeB));
  $("#modeBRunBtn").addEventListener("click", () => task("Running Mode B", runModeACycleOnce));
  $("#confirmModeCBtn").addEventListener("click", () => task("Confirming Mode C", confirmModeC));
  $("#cancelModeCSelectionBtn").addEventListener("click", () => cancelModeCSelection());
  $("#modeCRunBtn").addEventListener("click", () => task("Running Mode C", runModeACycleOnce));
  $("#modeCDebugBtn").addEventListener("click", () => task("Debug run", debugModeCPreview));
  $("#previewBtn").addEventListener("click", () => task("Previewing", previewJob));
  $("#moveSlowBtn").addEventListener("click", () => task("Moving", moveJobSlow));
  $("#stampDryBtn").addEventListener("click", () => task("Dry stamping", () => stampJob(true)));
  $("#stampLiveBtn").addEventListener("click", () => task("Live stamping", () => stampJob(false)));

  $("#scanSerialBtn").addEventListener("click", () => task("Scanning serial", scanSerialPorts));
  $("#serialConnectBtn").addEventListener("click", () => task("Connecting", connectSerial));
  $("#serialDisconnectBtn").addEventListener("click", () => task("Disconnecting", () => postSerial("/api/serial/disconnect")));
  $("#serialUnlockBtn").addEventListener("click", () => task("Unlocking", () => postSerial("/api/serial/unlock")));
  $("#serialStatusBtn").addEventListener("click", () => task("Status", () => postSerial("/api/serial/query")));
  $("#serialResetBtn").addEventListener("click", () => task("Reset", () => postSerial("/api/serial/reset")));
  ui.motionConnectBtn?.addEventListener("click", () => task("Motion connect", toggleMotionConnection));

  $$("[data-jogvec]").forEach((button) => {
    const [dx, dy, dz] = button.dataset.jogvec.split(",").map(Number);
    bindVectorHoldPress(button, dx, dy, dz);
  });

  $$("[data-jog]").forEach((button) => {
    const [axis, sign] = button.dataset.jog.split(":");
    const numericSign = Number(sign);
    bindAxisHoldPress(button, axis, numericSign);
  });

  const releaseAllHolds = () => {
    activeHoldReleases.forEach((release) => release());
  };
  window.addEventListener("pointerup", releaseAllHolds);
  window.addEventListener("pointercancel", releaseAllHolds);
  window.addEventListener("blur", () => {
    releaseAllHolds();
    if (draggingStampRegionPointIndex !== null) {
      draggingStampRegionPointIndex = null;
      draggingStampRegionPointerId = null;
      movedWhileDraggingStampRegion = false;
      ui.overlay.style.cursor = "";
    }
    if (draggingStampRegionEdgeIndex !== null) {
      draggingStampRegionEdgeIndex = null;
      draggingStampRegionEdgePointerId = null;
      draggingStampRegionLastPoint = null;
      movedWhileDraggingStampRegion = false;
      ui.overlay.style.cursor = "";
    }
    if (draggingCalPointIndex !== null) {
      draggingCalPointIndex = null;
      draggingCalPointerId = null;
      movedWhileDraggingCal = false;
      ui.overlay.style.cursor = "";
    }
  });

  $("#jogStepDownBtn").addEventListener("click", () => shiftJogStep(-1));
  $("#jogStepUpBtn").addEventListener("click", () => shiftJogStep(1));
  ui.jogStep.addEventListener("change", refreshMotionCalibrationReadout);
  $("#applyMeasuredScalesBtn").addEventListener("click", () => task("Applying measured scales", () => {
    applyMeasuredMotionScales();
    return Promise.resolve();
  }));
  $("#saveMotionScaleBtn").addEventListener("click", () => task("Saving motion calibration", saveMotionScaleSetting));
  $("#goXYZeroBtn").addEventListener("click", () => task("Going X0Y0", () => goZero("xy")));

  $("#captureOriginBtn").addEventListener("click", () => task("Set X0Y0", () => captureBoundsPoint("origin")));
  $("#captureXMaxBtn").addEventListener("click", () => task("Set X max", () => captureBoundsPoint("xMax")));
  $("#captureYMaxBtn").addEventListener("click", () => task("Set Y max", () => captureBoundsPoint("yMax")));
  $("#clearBoundsBtn").addEventListener("click", () => task("Clearing bounds", clearBounds));
  $("#applyBoundsBtn").addEventListener("click", () => task("Applying bounds", applyBounds));

  $("#rollerStepBtn").addEventListener("click", () => task("Paper step", () => runPaperFeed(Number(ui.rollerLength.value), 1)));
  const rollerFeedBtn = $("#rollerFeedBtn");
  bindRepeatPress(rollerFeedBtn, {
    tapAction: () => runPaperFeed(Number(ui.rollerLength.value), 1),
    repeatAction: () => runPaperFeed(Number(ui.rollerLength.value), 1),
    holdDelayMs: 260,
    holdIntervalMs: 320,
    actionName: "Paper feed",
    errorName: "Paper feed failed",
  });
  $("#savePaperFeedBtn").addEventListener("click", () => task("Saving feed setting", savePaperFeedSetting));

  $("#loadFirmwareSettingsBtn").addEventListener("click", () => task("Firmware settings", loadFirmwareSettings));
  $("#flashNowBtn").addEventListener("click", () => task("Flashing", flashFirmware));

  $("#nextCalPointBtn").addEventListener("click", nextCalPoint);
  $("#toggleCalibrationOverlayBtn").addEventListener("click", () => {
    cameraEditTarget = "calibration";
    toggleCalibrationOverlay();
  });
  $("#saveCalibrationBtn").addEventListener("click", () => task("Saving calibration", saveCalibration));
  $("#clearCalibrationBtn").addEventListener("click", () => task("Clearing calibration", clearCalibration));
  $("#setPaperRoiMachineBtn").addEventListener("click", () => task("Setting machine corner", setCurrentMachineForPaperRoi));
  $("#drawPaperRoiBtn").addEventListener("click", startStampRegionDraw);
  $("#nextStampRegionBoundBtn").addEventListener("click", nextStampRegionBoundPoint);
  $("#savePaperRoiBtn").addEventListener("click", () => task("Saving stamp/detect region", savePaperRoi));
  $("#saveStampRegionBoundBtn").addEventListener("click", () => task("Saving stamp region mapping", savePaperRoi));
  $("#toggleStampRegionOverlayBtn").addEventListener("click", () => {
    cameraEditTarget = "region";
    toggleStampRegionOverlay();
  });
  $("#clearStampRegionBoundBtn").addEventListener("click", () => task("Clearing stamp region machine corners", clearStampRegionMachinePoints));
  $("#clearPaperRoiBtn").addEventListener("click", () => task("Clearing stamp/detect region", clearPaperRoi));
  ui.activePaperRoiPoint?.addEventListener("change", () => {
    cameraEditTarget = "region";
    syncStampRegionCornerSelects(ui.activePaperRoiPoint.value);
  });
  ui.activeStampRegionBoundPoint?.addEventListener("change", () => {
    syncStampRegionCornerSelects(ui.activeStampRegionBoundPoint.value);
  });
}

bindEvents();
loadConfig()
  .then(() => Promise.allSettled([scanSerialPorts(), refreshSerialStatusOnly(), refreshRuntimeBounds()]))
  .catch((error) => {
    log(error.message);
    setStatus("Config error");
  });
