'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function Chat() {
  const { data: session, status } = useSession();
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  // Add loading state for chat
  if (status === 'loading') {
    return (
      <Card className="w-full max-w-2xl">
        <CardContent>
          <p>Loading...</p>
        </CardContent>
      </Card>
    );
  }

  const sendMessage = async () => {
    if (!message.trim() || !session?.accessToken) return;

    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message,
          access_token: session.accessToken,
        }),
      });

      const data = await res.json();
      setResponse(data.response);
    } catch (error) {
      console.error('Error:', error);
      setResponse('Error sending message');
    } finally {
      setLoading(false);
    }
  };

  if (!session) {
    return null;
  }

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle>Chat with MaxAI</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex space-x-2">
          <Input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type your message..."
          />
          <Button onClick={sendMessage} disabled={loading}>
            {loading ? 'Sending...' : 'Send'}
          </Button>
        </div>
        {response && (
          <div className="p-4 bg-muted rounded-lg">
            <p className="text-sm font-medium">Response:</p>
            <p>{response}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}