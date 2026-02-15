"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useToast } from "@/hooks/use-toast";
import {
  register,
  login as apiLogin,
  getProjects,
  ApiError,
  RegisterResponse,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { GoogleIcon } from "@/components/icons/google";
import { GitHubIcon } from "@/components/icons/github";
import { UserPlusIcon } from "@heroicons/react/24/outline";
import { XCircleIcon } from "@heroicons/react/24/solid";
import { Transition } from "@headlessui/react";

const useIAP = process.env.NEXT_PUBLIC_USE_IAP === "true";

export default function RegisterPage() {
  const [name, setName] = useState("");
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
  const { toast } = useToast();
  const { login } = useAuth();
  const { data: session, status } = useSession();

  // In IAP mode, redirect to login (Google handles registration)
  useEffect(() => {
    if (useIAP) {
      router.replace("/login");
    }
  }, [router]);

  // Fetch available OAuth providers on mount
  useEffect(() => {
    fetch("/api/auth/providers")
      .then((res) => res.json())
      .then((data) => setOauthProviders(data))
      .catch(() => setOauthProviders({ github: false, google: false }));
  }, []);

  // Track if we're processing OAuth callback
  const [processingOAuth, setProcessingOAuth] = useState(false);

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

        if (isNewUser) {
          toast({
            title: "Account created",
            description: "Welcome to Mai-Tai! 🍹",
          });
        }

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
  }, [session, status, login, router, toast]);

  // Check for OAuth error in URL
  useEffect(() => {
    const errorParam = searchParams.get("error");
    if (errorParam) {
      setError("OAuth authentication failed. Please try again.");
    }
  }, [searchParams]);

  const handleGoogleSignUp = () => {
    setOauthLoading("google");
    signIn("google", { callbackUrl: "/register" });
  };

  const handleGitHubSignUp = () => {
    setOauthLoading("github");
    signIn("github", { callbackUrl: "/register" });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      // Register with auto-provisioning
      const regResponse: RegisterResponse = await register(
        name,
        email,
        password,
      );

      // Log in to get tokens
      const loginResponse = await apiLogin(email, password);
      login(loginResponse.access_token, loginResponse.refresh_token);

      // Store provisioning data for the chat page
      sessionStorage.setItem(
        "mai-tai-onboarding",
        JSON.stringify({
          workspaceId: regResponse.workspace.id,
          apiKey: regResponse.api_key.key,
        }),
      );

      toast({
        title: "Account created",
        description: "Welcome to Mai-Tai! 🍹",
      });

      // Small delay to let auth state propagate before navigation
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Redirect to workspace chat
      // Note: Don't set isLoading=false here - keep showing loading screen until navigation completes
      router.push(`/workspaces/${regResponse.workspace.id}?onboarding=true`);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Please try again";
      setError(message);
      toast({
        variant: "destructive",
        title: "Registration failed",
        description: message,
      });
      // Only reset loading on error - on success, keep loading screen until navigation
      setIsLoading(false);
    }
  };

  // Show nothing while redirecting in IAP mode
  if (useIAP) {
    return null;
  }

  // Show loading screen while processing OAuth callback or email/password registration
  if (processingOAuth || status === "loading" || isLoading) {
    return (
      <div className="relative flex min-h-screen flex-col items-center justify-center bg-gray-900">
        {/* Background gradient */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-1/2 -left-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-purple-500/20 to-indigo-600/20 blur-3xl" />
          <div className="absolute -bottom-1/2 -right-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-indigo-500/10 to-purple-600/10 blur-3xl" />
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
        <div className="absolute -top-1/2 -left-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-purple-500/20 to-indigo-600/20 blur-3xl" />
        <div className="absolute -bottom-1/2 -right-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-indigo-500/10 to-purple-600/10 blur-3xl" />
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

      {/* Register card */}
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
              Create a local account
            </h2>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <input
                  id="name"
                  type="text"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
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
                  placeholder="Password (min 6 characters)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-3 text-base font-medium text-white shadow-lg shadow-indigo-500/25 transition hover:from-indigo-500 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <UserPlusIcon className="h-5 w-5" />
                {isLoading ? "Creating account..." : "Create local account"}
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
                      onClick={handleGitHubSignUp}
                      disabled={!!oauthLoading || isLoading}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-600 bg-gray-700/50 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <GitHubIcon className="h-5 w-5" />
                      {oauthLoading === "github" ? "Connecting..." : "GitHub"}
                    </button>
                  )}
                  {oauthProviders.google && (
                    <button
                      type="button"
                      onClick={handleGoogleSignUp}
                      disabled={!!oauthLoading || isLoading}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-600 bg-gray-700/50 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <GoogleIcon className="h-5 w-5" />
                      {oauthLoading === "google" ? "Connecting..." : "Google"}
                    </button>
                  )}
                </div>
              </>
            )}

            <p className="mt-6 text-center text-sm text-gray-400">
              Already have an account?{" "}
              <Link
                href="/login"
                className="font-medium text-indigo-400 transition hover:text-indigo-300"
              >
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
