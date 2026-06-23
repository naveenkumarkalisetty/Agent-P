'use client';
import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, ArrowRight, Sparkles } from 'lucide-react';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';

export default function LandingPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);

  const handleLaunch = () => {
    setIsNavigating(true);
    setTimeout(() => {
      router.push('/agent');
    }, 2500); // Show lottie animation before navigating
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <div className="relative min-h-screen w-full flex flex-col items-center justify-center overflow-hidden bg-zinc-50 dark:bg-zinc-950 transition-colors duration-500">
      
      {/* Background ambient lighting */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-emerald-500/10 dark:bg-emerald-500/20 blur-[120px] mix-blend-screen animate-pulse" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] rounded-full bg-cyan-500/10 dark:bg-cyan-500/20 blur-[150px] mix-blend-screen animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      {/* Loader Overlay */}
      {isNavigating && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-white transition-all duration-500 animate-[fade-in-up_0.5s_ease-out_forwards]">
          <div className="w-72 h-72">
            <DotLottieReact
              src="https://lottie.host/29f5d6e4-bff8-48e1-9825-d4c691221852/XN3EwZABng.lottie"
              loop
              autoplay
            />
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="relative z-10 flex flex-col items-center text-center px-6 max-w-4xl mx-auto">
        
        {/* Animated Icon */}
        <div className="relative mb-8 group">
          <div className="absolute inset-0 bg-emerald-500/20 blur-2xl rounded-full scale-150 group-hover:bg-emerald-400/30 transition-all duration-700" />
          <div className="relative flex items-center justify-center w-24 h-24 rounded-3xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl shadow-emerald-500/10">
            <Bot className="w-12 h-12 text-emerald-500 dark:text-emerald-400" />
          </div>
        </div>

        {/* Hero Text */}
        <h1 className="text-5xl md:text-7xl font-black text-zinc-900 dark:text-white tracking-tight mb-6 opacity-0 animate-[fade-in-up_1s_ease-out_forwards]">
          Meet <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-500 to-cyan-500">Agent-P</span>
        </h1>
        
        <p className="text-lg md:text-xl text-zinc-600 dark:text-zinc-400 mb-10 max-w-2xl opacity-0 animate-[fade-in-up_1s_ease-out_0.3s_forwards]">
          Your autonomous browser pilot. Hand over the tedious web forms and data entry, and watch as it seamlessly navigates, extracts, and submits on your behalf.
        </p>

        {/* CTA Button */}
        <div className="opacity-0 animate-[fade-in-up_1s_ease-out_0.6s_forwards] flex flex-col items-center gap-4">
          <button
            onClick={handleLaunch}
            className="group relative inline-flex items-center justify-center gap-3 px-8 py-4 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 font-bold rounded-full overflow-hidden transition-transform hover:scale-105 active:scale-95 shadow-xl shadow-zinc-900/20 dark:shadow-white/20"
          >
            <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-emerald-500 to-cyan-500 opacity-0 group-hover:opacity-10 transition-opacity duration-300" />
            <Sparkles className="w-5 h-5 text-emerald-400 dark:text-emerald-500" />
            <span>Launch Pilot Workspace</span>
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
          <span className="text-sm text-zinc-500 dark:text-zinc-500">
            Press to initialize the agent sandbox
          </span>
        </div>

      </div>

      <style>{`
        @keyframes fade-in-up {
          0% {
            opacity: 0;
            transform: translateY(20px);
          }
          100% {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
