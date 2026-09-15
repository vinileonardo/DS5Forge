import { BookOpen, Download, LockKeyhole, Save, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorText,
  Field,
  Notice,
  PageHeader,
} from "../../components/ui";
import { ApiError } from "../../lib/api/errors";
import type { Config, ControllerProfile, ProfileSummary, RuntimeState } from "../../lib/api/contracts";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";

type PendingOverwrite = {
  name: string;
  profile?: ControllerProfile;
  content?: string;
};

export function ProfilesPage() {
  const {
    profiles,
    config,
    runtime,
    coreStatus,
    stale,
    loadControllerProfile,
    saveControllerProfile,
    exportProfile,
    importProfile,
    deleteProfile,
  } = useRuntime();
  const [newName, setNewName] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [unsupportedSections, setUnsupportedSections] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [profileToDelete, setProfileToDelete] = useState<ProfileSummary | null>(null);
  const [profileToOverwrite, setProfileToOverwrite] = useState<PendingOverwrite | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  async function apply(name: string) {
    setPending(name);
    setError(null);
    setMessage(null);
    setUnsupportedSections([]);
    try {
      const response = await loadControllerProfile(name);
      setUnsupportedSections(response.unsupported_sections);
      setMessage(`Profile “${name}” applied.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function saveNew() {
    const name = newName.trim();
    if (!name || !config || !runtime) return;
    if (
      profiles.some(
        (profile) => profile.name.toLocaleLowerCase() === name.toLocaleLowerCase() && !profile.editable,
      )
    ) {
      setError(new Error("Bundled profile names are reserved and cannot be overwritten."));
      return;
    }
    const profile = buildControllerProfile(name, config, runtime);
    setPending("__save__");
    setError(null);
    setMessage(null);
    setUnsupportedSections([]);
    try {
      await saveControllerProfile(name, profile);
      setNewName("");
      setMessage(`Full Controller Lab profile “${name}” saved.`);
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "profile.overwrite_required") {
        setProfileToOverwrite({ name, profile });
      }
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function importFile(file: File) {
    setPending("__import__");
    setError(null);
    setMessage(null);
    setUnsupportedSections([]);
    try {
      if (file.size > 64 * 1024) throw new Error("Profile import is larger than the 64 KiB limit.");
      const content = await file.text();
      const imported = await importProfile(content);
      setMessage(`Profile “${imported.name}” imported.`);
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "profile.overwrite_required") {
        const content = await file.text();
        setProfileToOverwrite({
          name: profileNameFromContent(content) ?? safeProfileName(file.name),
          content,
        });
      }
      setError(reason);
    } finally {
      setPending(null);
      if (importInput.current) importInput.current.value = "";
    }
  }

  async function confirmOverwrite() {
    if (!profileToOverwrite) return;
    setPending(profileToOverwrite.name);
    setError(null);
    setUnsupportedSections([]);
    try {
      if (profileToOverwrite.profile) {
        await saveControllerProfile(profileToOverwrite.name, profileToOverwrite.profile, true);
      } else if (profileToOverwrite.content) {
        await importProfile(profileToOverwrite.content, undefined, true);
      }
      setMessage(`Profile “${profileToOverwrite.name}” overwritten after confirmation.`);
      setProfileToOverwrite(null);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function confirmDelete() {
    if (!profileToDelete) return;
    setPending(profileToDelete.name);
    setError(null);
    setUnsupportedSections([]);
    try {
      await deleteProfile(profileToDelete.name);
      setMessage(`Profile “${profileToDelete.name}” deleted.`);
      setProfileToDelete(null);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function exportOne(name: string) {
    setExporting(name);
    setError(null);
    setUnsupportedSections([]);
    try {
      const profile = await exportProfile(name);
      const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${profile.name}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage(`Profile “${name}” exported.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setExporting(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Reusable tuning"
        title="Profiles"
        description="Apply bundled presets safely or save, import and export a complete Controller Lab profile."
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title="Local core unavailable">
          Profile operations require the local service. Bundled and user data are never invented in the
          browser.
        </Notice>
      )}
      {message && (
        <Notice tone="success" title="Done">
          {message}
        </Notice>
      )}
      {unsupportedSections.length > 0 && (
        <Notice tone="warning" title="Some profile sections were not applied">
          The connected runtime does not support: {unsupportedSections.join(", ")}. Those sections were left
          untouched and no unsupported output was sent to the controller.
        </Notice>
      )}
      <ErrorText error={error} />
      {error instanceof ApiError && Object.keys(error.fields).length > 0 && (
        <Notice tone="danger" title="The core rejected this profile">
          Check the profile name and values, then try again.
        </Notice>
      )}
      <div className="stack">
        <Card>
          <div className="card-header">
            <div>
              <h2>Save current Controller Lab state</h2>
              <p>
                Rumble, lightbar, trigger, stick metadata and touchpad gesture sections are validated before
                persistence.
              </p>
            </div>
            <Save size={18} color="var(--accent)" />
          </div>
          <div className="card-grid grid-2">
            <Field
              label="New user profile name"
              help="Use letters, numbers, spaces, dots, underscores or hyphens. Bundled names are reserved."
            >
              <input
                className="input"
                aria-label="New user profile name"
                value={newName}
                disabled={coreStatus !== "online" || pending !== null || !runtime}
                maxLength={64}
                placeholder="e.g. Late night"
                onChange={(event) => setNewName(event.target.value)}
              />
            </Field>
            <div style={{ display: "flex", alignItems: "end" }}>
              <Button
                onClick={() => void saveNew()}
                disabled={
                  !newName.trim() || !config || !runtime || coreStatus !== "online" || pending !== null
                }
              >
                {pending === "__save__" ? "Saving…" : "Save profile"}
              </Button>
            </div>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Import and export</h2>
              <p>
                Imports use browser File/JSON content only and never change active state until explicitly
                applied.
              </p>
            </div>
            <Upload size={18} color="var(--accent)" />
          </div>
          <input
            ref={importInput}
            className="sr-only"
            type="file"
            accept="application/json,.json"
            aria-label="Import controller profile"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importFile(file);
            }}
          />
          <div className="form-actions profile-import-actions">
            <span className="muted">Strict schema-v2 JSON · maximum 64 KiB</span>
            <Button
              onClick={() => importInput.current?.click()}
              disabled={coreStatus !== "online" || pending !== null}
            >
              <Upload size={15} /> {pending === "__import__" ? "Importing…" : "Import JSON"}
            </Button>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Available profiles</h2>
              <p>Bundled presets are read-only. User profiles can be removed after confirmation.</p>
            </div>
            <BookOpen size={18} color="var(--violet)" />
          </div>
          {profiles.length === 0 ? (
            <EmptyState
              title="No profiles returned"
              description="Start the local core to load bundled and user profiles."
            />
          ) : (
            <div className="profile-list">
              {profiles.map((profile) => (
                <ProfileRow
                  key={profile.name}
                  profile={profile}
                  active={!stale && runtime?.active_profile === profile.name}
                  pending={pending === profile.name}
                  disabled={coreStatus !== "online" || pending !== null}
                  exporting={exporting === profile.name}
                  onApply={() => void apply(profile.name)}
                  onDelete={() => setProfileToDelete(profile)}
                  onExport={() => void exportOne(profile.name)}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
      {profileToDelete && (
        <ConfirmDialog
          title={`Delete “${profileToDelete.name}”?`}
          description="This removes the editable user profile from local storage. Bundled profiles cannot be deleted."
          confirmLabel="Delete profile"
          busyLabel="Deleting…"
          busy={pending === profileToDelete.name}
          onCancel={() => setProfileToDelete(null)}
          onConfirm={() => void confirmDelete()}
        />
      )}
      {profileToOverwrite && (
        <ConfirmDialog
          title={`Overwrite “${profileToOverwrite.name}”?`}
          description="This replaces an existing editable profile. The core has already validated every section; confirm the overwrite explicitly."
          confirmLabel="Overwrite profile"
          busyLabel="Overwriting…"
          busy={pending === profileToOverwrite.name}
          onCancel={() => setProfileToOverwrite(null)}
          onConfirm={() => void confirmOverwrite()}
        />
      )}
    </>
  );
}

function ProfileRow({
  profile,
  active,
  pending,
  disabled,
  onApply,
  onDelete,
  onExport,
  exporting,
}: {
  profile: ProfileSummary;
  active: boolean;
  pending: boolean;
  disabled: boolean;
  onApply: () => void;
  onDelete: () => void;
  onExport: () => void;
  exporting: boolean;
}) {
  return (
    <div className="profile-row">
      <div className="profile-main">
        <div className="profile-icon">
          {profile.editable ? <Upload size={15} /> : <LockKeyhole size={15} />}
        </div>
        <div>
          <div className="profile-name">
            {profile.name} {active && <span className="tag tag-active">Active</span>}
          </div>
          <div className="profile-meta">
            {profile.source === "bundled" ? "Bundled · read-only" : "User profile · editable"}
          </div>
        </div>
      </div>
      <div className="profile-actions">
        <Button
          variant="quiet"
          disabled={disabled || exporting}
          onClick={onExport}
          aria-label={`Export ${profile.name}`}
        >
          <Download size={14} /> {exporting ? "Exporting…" : "Export"}
        </Button>
        <Button variant="quiet" disabled={disabled} onClick={onApply}>
          {pending ? "Applying…" : "Apply"}
        </Button>
        {profile.editable && (
          <Button
            variant="danger"
            disabled={disabled}
            aria-label={`Delete ${profile.name}`}
            onClick={onDelete}
          >
            <Trash2 size={14} /> Delete
          </Button>
        )}
      </div>
    </div>
  );
}

function buildControllerProfile(name: string, config: Config, runtime: RuntimeState): ControllerProfile {
  const lightbar = runtime.lightbar ?? {
    r: 0,
    g: 0,
    b: 0,
    enabled: true,
    brightness: 2,
    pulse: "off" as const,
  };
  const triggers = runtime.triggers ?? {
    left: {
      mode: "off" as const,
      start_position: 0,
      end_position: 255,
      force: 0,
      frequency: 0,
      amplitude: 0,
    },
    right: {
      mode: "off" as const,
      start_position: 0,
      end_position: 255,
      force: 0,
      frequency: 0,
      amplitude: 0,
    },
    preview: null,
  };
  const sticks = runtime.stick_calibration ?? {
    left_deadzone: 0.08,
    right_deadzone: 0.08,
    left_center_x: 0,
    left_center_y: 0,
    right_center_x: 0,
    right_center_y: 0,
  };
  const gestures = runtime.gesture_config ?? {
    enabled: true,
    two_finger_scroll: true,
    tap_to_click: true,
    swipe_enabled: true,
    swipe_threshold: 40,
  };
  return {
    schema_version: 2,
    name,
    rumble: config.rumble,
    lightbar,
    triggers: { left: triggers.left, right: triggers.right },
    sticks,
    touchpad: {
      enabled: gestures.enabled,
      two_finger_scroll: gestures.two_finger_scroll,
      tap_to_click: gestures.tap_to_click,
      swipe_enabled: gestures.swipe_enabled,
      swipe_threshold: gestures.swipe_threshold,
    },
  };
}

function profileNameFromContent(content: string): string | undefined {
  try {
    const value: unknown = JSON.parse(content);
    if (typeof value === "object" && value !== null && "name" in value && typeof value.name === "string") {
      return value.name;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function safeProfileName(fileName: string): string {
  const stem = fileName.replace(/\.json$/i, "").trim();
  return /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/.test(stem) ? stem : "Imported profile";
}
