import { Check, MonitorCog, Palette, Save } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  LoadingState,
  Notice,
  PageHeader,
  Select,
} from "../../components/ui";
import type { Config } from "../../lib/api/contracts";
import { API_BASE_URL } from "../../lib/api/client";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";

const themes: Config["theme"][] = ["Dark", "Light", "Liquid Glass"];
const micBehaviors: Array<{ value: Config["mic_button"]; label: string; help: string }> = [
  { value: "master", label: "Master behavior", help: "Toggle the master behavior defined by the core." },
  { value: "rumble", label: "Haptics", help: "Toggle audio-driven rumble from the controller button." },
  {
    value: "trackpad",
    label: "Touchpad",
    help: "Toggle touchpad mouse behavior from the controller button.",
  },
];

export function SettingsPage() {
  const { config, coreStatus, updateConfig } = useRuntime();
  const [theme, setTheme] = useState<Config["theme"]>(config?.theme ?? "Dark");
  const [micButton, setMicButton] = useState<Config["mic_button"]>(config?.mic_button ?? "master");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (config) {
      setTheme(config.theme);
      setMicButton(config.mic_button);
    }
  }, [config]);

  if (!config) {
    return coreStatus === "online" ? (
      <LoadingState label="Waiting for persisted settings from the local core…" />
    ) : (
      <>
        <PageHeader
          eyebrow="Client and core preferences"
          title="Settings"
          description="Persisted settings come from the local core."
        />
        <EmptyState
          title="Settings unavailable"
          description="Start the local core to load persisted preferences. The browser will retry without creating defaults."
        />
      </>
    );
  }

  const dirty = theme !== config.theme || micButton !== config.mic_button;
  async function save() {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await updateConfig({ theme, mic_button: micButton });
      setMessage("Settings saved.");
    } catch (reason) {
      setError(reason);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Client and core preferences"
        title="Settings"
        description="Keep the existing schema-v1 preferences visible without introducing a second local configuration system."
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title="Core unavailable">
          Settings are read-only until the local Python core responds.
        </Notice>
      )}
      {message && (
        <Notice tone="success" title="Saved">
          <Check size={14} />
          {message}
        </Notice>
      )}
      <ErrorText error={error} />
      <div className="stack">
        <Card>
          <div className="card-header">
            <div>
              <h2>Appearance</h2>
              <p>
                The existing persisted theme remains authoritative. Dark is the P1 default only when no saved
                value exists.
              </p>
            </div>
            <Palette size={18} color="var(--accent)" />
          </div>
          <Field label="Theme" help="Liquid Glass remains available when it is present in the core contract.">
            <Select
              aria-label="Theme"
              value={theme}
              disabled={coreStatus !== "online" || saving}
              onChange={(event) => setTheme(event.target.value as Config["theme"])}
            >
              {themes.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </Field>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Microphone button behavior</h2>
              <p>These labels map directly to the current `master`, `rumble` and `trackpad` wire values.</p>
            </div>
            <MonitorCog size={18} color="var(--violet)" />
          </div>
          <Field label="Button action" help={micBehaviors.find((item) => item.value === micButton)?.help}>
            <Select
              aria-label="Microphone button behavior"
              value={micButton}
              disabled={coreStatus !== "online" || saving}
              onChange={(event) => setMicButton(event.target.value as Config["mic_button"])}
            >
              {micBehaviors.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="form-actions">
            <span className="muted">{dirty ? "Unsaved settings" : "Settings are up to date."}</span>
            <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
              <Save size={15} />
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Local service</h2>
              <p>Informational only. P1 does not expose an arbitrary endpoint editor.</p>
            </div>
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>API endpoint</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>Transport scope</dt>
              <dd>USB / wired only</dd>
            </div>
            <div className="data-item">
              <dt>Core start</dt>
              <dd>
                <code>python source/run.py --headless</code>
              </dd>
            </div>
          </dl>
        </Card>
      </div>
    </>
  );
}
