// Speaks the raw Streamlit static-component postMessage protocol directly
// (see index.html for why: this needs no more than "I'm ready" and "here
// are new args", so pulling in streamlit-component-lib isn't worth it).
const metricEl = document.getElementById("metric");
const labelEl = document.getElementById("label");
const valueEl = document.getElementById("value");

// The host's top-level message dispatcher (ComponentRegistry) drops
// anything without this flag before it ever reaches per-component
// handling - silently, with no console warning either side.
function post(message) {
  window.parent.postMessage({ isStreamlitMessage: true, ...message }, "*");
}

function sendHeight() {
  post({
    type: "streamlit:setFrameHeight",
    height: document.documentElement.scrollHeight,
  });
}

function render(args) {
  labelEl.textContent = args.label;
  metricEl.classList.toggle("bordered", !!args.border);

  valueEl.style.color = args.color || "#15171C";
  valueEl.format =
    args.decimals == null
      ? { maximumFractionDigits: 8 }
      : { minimumFractionDigits: args.decimals, maximumFractionDigits: args.decimals };
  valueEl.numberPrefix = args.prefix || "";
  valueEl.numberSuffix = args.suffix || "";
  valueEl.update(args.value);
}

// A single post-update measurement isn't enough: NumberFlow's own
// transition (~900ms, see its `transformTiming`) keeps resizing the
// element as digits are added/removed, so the frame's height has to
// keep tracking it for the rest of the animation too, not just its
// very first frame.
new ResizeObserver(sendHeight).observe(metricEl);

window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "streamlit:render") {
    render(event.data.args);
  }
});
post({ type: "streamlit:componentReady", apiVersion: 1 });
