'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import LandingPage from './(public)/landing/page';

export default function Home() {
  const { token, isLoading } = useAuth();
  const router = useRouter();

  // If logged in, redirect to dashboard
  useEffect(() => {
    if (!isLoading && token) {
      router.push('/dashboard');
    }
  }, [token, isLoading, router]);

  // Show loading while checking auth
  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </main>
    );
  }

  // If not logged in, show landing page
  if (!token) {
    return <LandingPage />;
  }

  // Redirecting to dashboard...
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </main>
  );
}

