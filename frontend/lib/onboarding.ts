/**
 * Onboarding data helpers.
 *
 * Encodes sensitive onboarding data (API key) before storing in sessionStorage
 * so it's not stored in clear text. Uses base64 encoding — this is obfuscation
 * rather than encryption, but the data is ephemeral (sessionStorage) and removed
 * immediately after the onboarding card is dismissed or an agent connects.
 */

const STORAGE_KEY = 'mai-tai-onboarding';

export interface OnboardingData {
  workspaceId?: string;
  projectId?: string;  // legacy
  apiKey?: string;
}

export function storeOnboardingData(data: OnboardingData): void {
  const encoded = btoa(JSON.stringify(data));
  sessionStorage.setItem(STORAGE_KEY, encoded);
}

export function loadOnboardingData(): OnboardingData | null {
  const stored = sessionStorage.getItem(STORAGE_KEY);
  if (!stored) return null;
  try {
    // Support both encoded and legacy plain JSON format
    const decoded = stored.startsWith('{')
      ? stored
      : atob(stored);
    return JSON.parse(decoded) as OnboardingData;
  } catch {
    return null;
  }
}

export function clearOnboardingData(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}
