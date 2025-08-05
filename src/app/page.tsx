import GoogleLogin from '@/components/GoogleLogin'; 
import Chat from '@/components/Chat';

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="w-full max-w-md">
        <GoogleLogin />
        <Chat />
      </div>
    </main>
  );
}