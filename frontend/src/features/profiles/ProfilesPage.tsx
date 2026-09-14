import { BookOpen, LockKeyhole, Save, Trash2, Upload } from "lucide-react";
import { useState } from "react";

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
import { useRuntime } from "../../lib/runtime/RuntimeProvider";
import type { ProfileSummary } from "../../lib/api/contracts";

export function ProfilesPage() {
  const { profiles, config, runtime, coreStatus, stale, loadProfile, saveProfile, deleteProfile } =
    useRuntime();
  const [newName, setNewName] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [profileToDelete, setProfileToDelete] = useState<ProfileSummary | null>(null);

  async function apply(name: string) {
    setPending(name);
    setError(null);
    setMessage(null);
    try {
      await loadProfile(name);
      setMessage(`Profile “${name}” applied.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function saveNew() {
    const name = newName.trim();
    if (!name || !config) return;
    if (
      profiles.some(
        (profile) => profile.name.toLocaleLowerCase() === name.toLocaleLowerCase() && !profile.editable,
      )
    ) {
      setError(new Error("Bundled profile names are reserved and cannot be overwritten."));
      return;
    }
    setPending("__save__");
    setError(null);
    setMessage(null);
    try {
      await saveProfile(name, config.rumble);
      setNewName("");
      setMessage(`Profile “${name}” saved.`);
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

  return (
    <>
      <PageHeader
        eyebrow="Reusable tuning"
        title="Profiles"
        description="Apply bundled presets safely or save your current haptics configuration as an editable user profile."
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
              <h2>Save current haptics</h2>
              <p>The current rumble values are sent to the core and validated before persistence.</p>
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
                disabled={coreStatus !== "online" || pending !== null}
                maxLength={64}
                placeholder="e.g. Late night"
                onChange={(event) => setNewName(event.target.value)}
              />
            </Field>
            <div style={{ display: "flex", alignItems: "end" }}>
              <Button
                onClick={() => void saveNew()}
                disabled={!newName.trim() || !config || coreStatus !== "online" || pending !== null}
              >
                {pending === "__save__" ? "Saving…" : "Save profile"}
              </Button>
            </div>
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
                  onApply={() => void apply(profile.name)}
                  onDelete={() => setProfileToDelete(profile)}
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
          busy={pending === profileToDelete.name}
          onCancel={() => setProfileToDelete(null)}
          onConfirm={() => void confirmDelete()}
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
}: {
  profile: ProfileSummary;
  active: boolean;
  pending: boolean;
  disabled: boolean;
  onApply: () => void;
  onDelete: () => void;
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
            <Trash2 size={14} />
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}
