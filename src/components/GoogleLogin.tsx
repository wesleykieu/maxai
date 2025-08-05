'use client';

import { signIn, signOut, useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function GoogleLogin() {

  const { data: session, status } = useSession();

  // Add loading state
  if (status === 'loading') {
    return (
      <Card className="w-full max-w-md">
        <CardContent>
          <p>Loading...</p>
        </CardContent>
      </Card>
    );
  }

  if (session) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Welcome back!</CardTitle>
          <CardDescription>You're successfully signed in</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center space-x-2">
            <Badge variant="secondary">Email</Badge>
            <span className="text-sm">{session.user?.email}</span>
          </div>
          <div className="flex items-center space-x-2">
            <Badge variant="outline">Access Token</Badge>
            <span className="text-xs font-mono text-muted-foreground">
              {session.accessToken?.substring(0, 20)}...
            </span>
          </div>
          <Button 
            onClick={() => signOut()}
            className="w-full"
          >
            Sign out
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>MaxAI Productivity Assistant</CardTitle>
        <CardDescription>Sign in to access your calendar and schedule meetings</CardDescription>
      </CardHeader>
      <CardContent>
        <Button 
          onClick={() => signIn('google')}
          className="w-full"
          size="lg"
        >
          Sign in with Google
        </Button>
      </CardContent>
    </Card>
  );
}