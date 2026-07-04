'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { ChatShortcutsProvider } from '@/lib/chat-shortcuts';
import Layout from '@/components/Layout';

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !token) {
      router.push('/login');
    }
  }, [token, isLoading, router]);

  // Show nothing while checking auth
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  // If not authenticated, show nothing (redirect will happen)
  if (!token) {
    return null;
  }

  return (
    <ChatShortcutsProvider>
      <Layout>{children}</Layout>
    </ChatShortcutsProvider>
  );
}

