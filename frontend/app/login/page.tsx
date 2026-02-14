"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useAuth } from "@/lib/auth";
import { GoogleIcon } from "@/components/icons/google";
import { GitHubIcon } from "@/components/icons/github";
import { login as apiLogin, getProjects, ApiError } from "@/lib/api";
import { ArrowLeftOnRectangleIcon } from "@heroicons/react/24/outline";
import { XCircleIcon } from "@heroicons/react/24/solid";
import { Transition } from "@headlessui/react";

const useIAP = process.env.NEXT_PUBLIC_USE_IAP === "true";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<"github" | "google" | null>(
    null,
  );
  const [error, setError] = useState("");
  const [oauthProviders, setOauthProviders] = useState<{
    github: boolean;
    google: boolean;
  }>({ github: false, google: false });
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const { data: session, status } = useSession();

  // Track if we're processing OAuth callback
  const [processingOAuth, setProcessingOAuth] = useState(false);

  // Fetch available OAuth providers on mount
  useEffect(() => {
    fetch("/api/auth/providers")
      .then((res) => res.json())
      .then((data) => setOauthProviders(data))
      .catch(() => setOauthProviders({ github: false, google: false }));
  }, []);

  // Handle OAuth callback - when session is established, log in to our auth system
  useEffect(() => {
    if (status === "authenticated" && session) {
      setProcessingOAuth(true);
      const accessToken = (session as any).accessToken;
      const refreshToken = (session as any).refreshToken;
      const isNewUser = (session as any).isNewUser;
      const provisionedWorkspace = (session as any).provisionedWorkspace;
      const provisionedApiKey = (session as any).provisionedApiKey;

      if (accessToken && refreshToken) {
        login(accessToken, refreshToken);

        // For new OAuth users, store onboarding data for the onboarding card
        if (isNewUser && provisionedWorkspace && provisionedApiKey) {
          sessionStorage.setItem(
            "mai-tai-onboarding",
            JSON.stringify({
              workspaceId: provisionedWorkspace.id,
              apiKey: provisionedApiKey.key,
            }),
          );
          // Redirect new users to their workspace with onboarding flag
          router.push(`/workspaces/${provisionedWorkspace.id}?onboarding=true`);
          return;
        }

        // Existing users: redirect to workspace or dashboard
        getProjects(accessToken)
          .then((response) => {
            if (response.projects.length > 0) {
              router.push(`/workspaces/${response.projects[0].id}`);
            } else {
              router.push("/dashboard");
            }
          })
          .catch(() => router.push("/dashboard"));
      }
    }
  }, [session, status, login, router]);

  // Check for OAuth error in URL
  useEffect(() => {
    const errorParam = searchParams.get("error");
    if (errorParam) {
      setError("OAuth sign-in failed. Please try again.");
    }
  }, [searchParams]);

  const handleGoogleSignIn = () => {
    if (useIAP) {
      window.location.href = "/dashboard";
    } else {
      setOauthLoading("google");
      signIn("google", { callbackUrl: "/login" });
    }
  };

  const handleGitHubSignIn = () => {
    setOauthLoading("github");
    signIn("github", { callbackUrl: "/login" });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      const response = await apiLogin(email, password);
      login(response.access_token, response.refresh_token);

      // Try to redirect to user's first workspace
      try {
        const workspacesResponse = await getProjects(response.access_token);
        if (workspacesResponse.projects.length > 0) {
          const firstWorkspace = workspacesResponse.projects[0];
          router.push(`/workspaces/${firstWorkspace.id}`);
          return;
        }
      } catch {
        // Fall back to dashboard if workspaces fetch fails
      }

      router.push("/dashboard");
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Please try again";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  // Show loading screen while processing OAuth callback
  if (processingOAuth || status === "loading") {
    return (
      <div className="relative flex min-h-screen flex-col items-center justify-center bg-gray-900">
        {/* Background gradient */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-1/2 -right-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-600/20 blur-3xl" />
          <div className="absolute -bottom-1/2 -left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-purple-500/10 to-indigo-600/10 blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col items-center">
          <img
            src="/logo.png"
            alt="Mai-Tai"
            className="h-20 w-20 rounded-full object-cover shadow-lg shadow-indigo-500/30 animate-pulse"
          />
          <h1 className="text-gradient mt-6 text-3xl font-bold">
            Setting up your workspace...
          </h1>
          <p className="mt-3 text-gray-400">
            Just a moment while we get everything ready
          </p>
          <div className="mt-8 flex space-x-2">
            <div
              className="h-2 w-2 rounded-full bg-indigo-500 animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <div
              className="h-2 w-2 rounded-full bg-indigo-500 animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <div
              className="h-2 w-2 rounded-full bg-indigo-500 animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen flex-col bg-gray-900 py-14">
      {/* Background gradient */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-1/2 -right-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-600/20 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-purple-500/10 to-indigo-600/10 blur-3xl" />
      </div>

      {/* Logo */}
      <div className="relative z-40 mt-10 flex flex-col items-center px-4 sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          href="/"
          className="flex items-center space-x-4 transition hover:opacity-80"
        >
          <img
            src="/logo.png"
            alt="Mai-Tai"
            className="h-16 w-16 rounded-full object-cover shadow-lg shadow-indigo-500/30"
          />
          <h1 className="text-gradient text-4xl font-bold">Mai-Tai</h1>
        </Link>
        <p className="mt-4 text-gray-400">Your data stays on your machine.</p>
      </div>

      {/* Login card */}
      <div className="relative z-50 mt-10 sm:mx-auto sm:w-full sm:max-w-md">
        <div
          className="mx-4 rounded-xl border border-gray-700 bg-gray-800/50 shadow-xl sm:mx-0"
          style={{ backdropFilter: "blur(12px)" }}
        >
          {/* Error message */}
          <Transition
            show={!!error}
            enter="transition-opacity duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="mx-4 mt-4 rounded-lg bg-red-600/90 p-4">
              <div className="flex">
                <XCircleIcon className="h-5 w-5 flex-shrink-0 text-red-200" />
                <p className="ml-3 text-sm font-medium text-red-100">{error}</p>
              </div>
            </div>
          </Transition>

          <div className="px-8 py-10 sm:px-10">
            <h2 className="mb-6 text-center text-xl font-bold text-gray-100">
              Sign in to continue
            </h2>

            {useIAP ? (
              /* Production: Google Sign-In via IAP */
              <div className="space-y-6">
                <button
                  onClick={handleGoogleSignIn}
                  className="flex w-full items-center justify-center gap-3 rounded-lg bg-white px-4 py-3 text-base font-medium text-gray-900 transition hover:bg-gray-100"
                >
                  <GoogleIcon className="h-5 w-5" />
                  Sign in with Google
                </button>
                <p className="text-center text-xs text-gray-500">
                  By signing in, you agree to our{" "}
                  <Link
                    href="/terms"
                    className="text-indigo-400 hover:text-indigo-300"
                  >
                    Terms
                  </Link>{" "}
                  and{" "}
                  <Link
                    href="/privacy"
                    className="text-indigo-400 hover:text-indigo-300"
                  >
                    Privacy Policy
                  </Link>
                </p>
              </div>
            ) : (
              /* Development: Email/Password form */
              <>
                <form onSubmit={handleSubmit} className="space-y-5">
                  <div>
                    <input
                      id="email"
                      type="email"
                      placeholder="Email address"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <input
                      id="password"
                      type="password"
                      placeholder="Password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-3 text-base font-medium text-white shadow-lg shadow-indigo-500/25 transition hover:from-indigo-500 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <ArrowLeftOnRectangleIcon className="h-5 w-5" />
                    {isLoading ? "Signing in..." : "Sign in"}
                  </button>
                </form>

                {/* OAuth section - only show if at least one provider is configured */}
                {(oauthProviders.github || oauthProviders.google) && (
                  <>
                    <div className="mt-6 flex items-center">
                      <div className="flex-grow border-t border-gray-600" />
                      <span className="mx-4 flex-shrink text-sm text-gray-500">
                        or continue with
                      </span>
                      <div className="flex-grow border-t border-gray-600" />
                    </div>

                    {/* OAuth Buttons */}
                    <div className="mt-6 flex gap-3">
                      {oauthProviders.github && (
                        <button
                          type="button"
                          onClick={handleGitHubSignIn}
                          disabled={!!oauthLoading}
                          className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-600 bg-gray-700/50 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <GitHubIcon className="h-5 w-5" />
                          {oauthLoading === "github"
                            ? "Signing in..."
                            : "GitHub"}
                        </button>
                      )}
                      {oauthProviders.google && (
                        <button
                          type="button"
                          onClick={handleGoogleSignIn}
                          disabled={!!oauthLoading}
                          className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-600 bg-gray-700/50 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <GoogleIcon className="h-5 w-5" />
                          {oauthLoading === "google"
                            ? "Signing in..."
                            : "Google"}
                        </button>
                      )}
                    </div>
                  </>
                )}

                <p className="mt-6 text-center text-sm text-gray-400">
                  Don&apos;t have an account?{" "}
                  <Link
                    href="/register"
                    className="font-medium text-indigo-400 transition hover:text-indigo-300"
                  >
                    Create an account
                  </Link>
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
