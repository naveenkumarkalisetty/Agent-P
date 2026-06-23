'use client';
import React, { useState, useEffect } from 'react';
import { Bot } from 'lucide-react';

const STATUS_MESSAGES = [
  'Scanning the form...',
  'Mapping fields to your profile...',
  'Analyzing input types...',
  'Getting everything ready...',
  'Almost there...',
];

export default function AgentLoadingAnimation() {
  const [messageIndex, setMessageIndex] = useState(0);
  const [isFading, setIsFading] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsFading(true);
      setTimeout(() => {
        setMessageIndex(prev => (prev + 1) % STATUS_MESSAGES.length);
        setIsFading(false);
      }, 400);
    }, 2800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full h-full flex flex-col items-center justify-center select-none overflow-hidden">
      {/* Background floating dots */}
      <div className="absolute inset-0 pointer-events-none">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="absolute w-2 h-2 rounded-full bg-zinc-600/30"
            style={{
              left: `${15 + i * 15}%`,
              top: `${20 + (i % 3) * 25}%`,
              animation: `floatDot ${3 + i * 0.5}s ease-in-out infinite alternate`,
              animationDelay: `${i * 0.4}s`,
            }}
          />
        ))}
      </div>

      {/* Bouncing Bot */}
      <div className="relative mb-8">
        {/* Glow ring */}
        <div
          className="absolute inset-0 rounded-full bg-emerald-500/10 blur-xl"
          style={{ animation: 'pulseGlow 2s ease-in-out infinite' }}
        />
        {/* Bot icon container */}
        <div
          className="
            relative w-20 h-20
            rounded-2xl
            bg-zinc-800 border border-zinc-700/50
            flex items-center justify-center
            shadow-2xl shadow-black/40
          "
          style={{ animation: 'botBounce 2s cubic-bezier(0.36, 0.07, 0.19, 0.97) infinite' }}
        >
          <Bot className="w-10 h-10 text-emerald-400" />
        </div>
        {/* Shadow under bot */}
        <div
          className="mx-auto mt-3 w-12 h-2 rounded-full bg-zinc-700/50 blur-sm"
          style={{ animation: 'shadowPulse 2s ease-in-out infinite' }}
        />
      </div>

      {/* Loading dots */}
      <div className="flex gap-2 mb-6">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-2.5 h-2.5 rounded-full bg-emerald-400"
            style={{
              animation: 'dotJump 1.4s ease-in-out infinite',
              animationDelay: `${i * 0.16}s`,
            }}
          />
        ))}
      </div>

      {/* Rotating status message */}
      <p
        className={`
          text-sm dark:text-zinc-400 font-medium
          text-zinc-700
          transition-all duration-400
          ${isFading ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'}
        `}
      >
        {STATUS_MESSAGES[messageIndex]}
      </p>

      {/* Inline keyframe styles */}
      <style>{`
        @keyframes botBounce {
          0%, 100% { transform: translateY(0); }
          30% { transform: translateY(-20px) rotate(-3deg); }
          50% { transform: translateY(-12px) rotate(2deg); }
          70% { transform: translateY(-16px) rotate(-1deg); }
        }
        @keyframes shadowPulse {
          0%, 100% { transform: scaleX(1); opacity: 0.5; }
          30% { transform: scaleX(0.6); opacity: 0.2; }
          50% { transform: scaleX(0.8); opacity: 0.35; }
          70% { transform: scaleX(0.7); opacity: 0.25; }
        }
        @keyframes dotJump {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-10px); opacity: 1; }
        }
        @keyframes floatDot {
          0% { transform: translate(0, 0); opacity: 0.3; }
          100% { transform: translate(10px, -15px); opacity: 0.6; }
        }
        @keyframes pulseGlow {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.4); opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}
