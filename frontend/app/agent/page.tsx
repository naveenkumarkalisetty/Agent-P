'use client';
import React, { useState, useEffect, useRef } from 'react';
import {
  SendHorizonalIcon, Bot, CircleStop, Sun, Moon
} from 'lucide-react';
import { ChatMessage, FormFieldElement, AgentProgressState } from '@/types/types';
import { ToastProvider, useToast } from '../components/Toast';
import AgentLoadingAnimation from '../components/AgentLoadingAnimation';

function PilotContent() {
  const { addToast } = useToast();
  const [isDark, setIsDark] = useState(true);

  const toggleTheme = () => {
    const html = document.documentElement;
    if (isDark) {
      html.classList.remove('dark');
    } else {
      html.classList.add('dark');
    }
    setIsDark(!isDark);
  };
  const [url, setUrl] = useState('');
  const [resume, setResume] = useState<File | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [isInitialized, setIsInitialized] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [liveImage, setLiveImage] = useState<string>("");
  const [isExecutionComplete, setIsExecutionComplete] = useState<boolean>(false);
  // Agent loop state
  const [agentState, setAgentState] = useState<AgentProgressState>({
    executionQueue: [],
    currentIndex: 0,
    isProcessing: false,
    currentUrl: '',
  });

  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleInitializeAgent = async () => {
    if (!url || !resume) return;

    setIsUploading(true);

    const formData = new FormData();
    formData.append('resume', resume)
    formData.append('url', url);

    try {
      const response = await fetch("http://localhost:8000/api/initiate-run", {
        method: 'POST',
        body: formData,
      });

      const data = await response.json()
      console.log('Parsed data from backend:', data)
      setAgentState(prev => ({
        ...prev,
        executionQueue: data.execution_queue,
        currentIndex: data.current_index
      }))
      setIsInitialized(true);
      setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'agent', text: 'Initialized successfully!', timestamp: new Date() }])
      addToast('Agent initialized — starting form fill!', 'success');

      // auto stream
      startStreaming()
    } catch (error) {
      console.error("Failed to parse data:", error)
      addToast('Failed to initialize agent.', 'error');
    } finally {
      setIsUploading(false);
    }
  }

  const startStreaming = async () => {
    setAgentState(prev => ({ ...prev, isProcessing: true }));
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('http://localhost:8000/api/stream-execution', {
        method: 'GET',
        signal: abortControllerRef.current.signal
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) return;
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf('\n\n');

        while (boundary !== -1) {
          const completeMessage = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);

          if (completeMessage.startsWith('data: ')) {
            try {
              const data = JSON.parse(completeMessage.replace('data: ', ''));

              if (data.type === 'FIELD_UPDATED') {
                setAgentState(prev => {
                  const updatedQueue = [...prev.executionQueue];
                  updatedQueue[data.currentIndex - 1] = data.field;
                  return { ...prev, executionQueue: updatedQueue, currentIndex: data.currentIndex };
                });

                if (data.liveImage) {
                  setLiveImage(`data:image/jpeg;base64,${data.liveImage}`);
                }

                setMessages(prev => [
                  ...prev,
                  {
                    id: crypto.randomUUID(),
                    sender: 'system',
                    text: `${data.field.status === 'completed' ? 'Filled' : "Ignored"} ${data.field.label}`,
                    timestamp: new Date()
                  }
                ]);

              } else if (data.type === 'EXECUTION_COMPLETE') {
                setAgentState(prev => ({ ...prev, isProcessing: false }));
                setMessages(prev => [...prev, { id: crypto.randomUUID(), sender: 'agent', text: 'Form automation complete!', timestamp: new Date() }]);
                setIsExecutionComplete(true);
                addToast('Form automation complete!', 'success');
                break;
              }
            } catch (err) {
              console.error("Failed to parse JSON message:", err);
            }
          }

          // Check if there is ANOTHER complete message waiting in the buffer
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('Stream halted by user.');
      } else {
        console.error("Stream error:", error);
      }
    }
  };

  const handleStopExecution = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setAgentState(prev => ({ ...prev, isProcessing: false }))
      setMessages(prev => [...prev, { id: crypto.randomUUID(), sender: 'agent', text: 'Execution paused. What would you like to change?', timestamp: new Date() }])
      addToast('Agent execution paused.', 'warning');
    }
  }

  const handleSendChatMessage = async (e: React.SubmitEvent) => {
    e.preventDefault();
    if (agentState.isProcessing || !chatInput.trim()) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      sender: 'user',
      text: chatInput,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = chatInput;
    setChatInput('');

    // Set processing immediately for instant button swap
    setAgentState(prev => ({ ...prev, isProcessing: true }));
    addToast('Instruction sent — resuming...', 'info');

    // send the correction
    const response = await fetch('http://localhost:8000/api/chat-instruction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: currentInput })
    });

    const data = await response.json();

    if (data.updated_fields && data.updated_fields.length > 0) {
      data.updated_fields.forEach((f: any) => {
        const action = f.value === "" ? "Skipped" : "Modified";
        setMessages(prev => [...prev, { id: crypto.randomUUID(), sender: 'system', text: `✦ ${action} ${f.label}`, timestamp: new Date() }]);
      });
    }

    // resume the stream
    startStreaming();
  };

  // Calculate dynamic progress metrics
  const totalFields = agentState.executionQueue?.length || 10;
  const completedFields = agentState.executionQueue?.filter(f => f.status === 'completed')?.length || 0;
  const progressPercentage = totalFields > 0 ? Math.round((completedFields / totalFields) * 100) : 0;
  return (
    <div className="
      h-screen w-full flex gap-5 p-5
      bg-[radial-gradient(circle_at_top_left,#6366f122,transparent_35%),radial-gradient(circle_at_bottom_right,#8b5cf622,transparent_40%),#f8fafc]
      dark:bg-[radial-gradient(circle_at_top_left,#4f46e522,transparent_35%),radial-gradient(circle_at_bottom_right,#7c3aed22,transparent_40%),#020617]
      overflow-hidden
      transition-all duration-500
      "
    >

      {/* LEFT PANE */}
      <div className="w-[35%]">
        <div
          className="
            relative h-full overflow-hidden
            rounded-[32px]
            border-2 border-zinc-400 dark:border-zinc-800/80
            bg-white dark:bg-zinc-900
            backdrop-blur-2xl
            shadow-xl shadow-zinc-300/50 dark:shadow-2xl dark:shadow-black/40
            flex flex-col
          "
        >
          {/* Subtle ambient light */}
          <div className="absolute inset-0">
            <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-zinc-700/10 blur-[120px]" />
            <div className="absolute bottom-0 right-0 w-80 h-80 rounded-full bg-zinc-600/8 blur-[140px]" />
          </div>

          {/* Header */}
          <div className="relative z-10 px-6 py-5 border-b border-zinc-200 dark:border-zinc-800/80 bg-gradient-to-r from-zinc-100 to-zinc-300 dark:from-zinc-800 dark:to-zinc-950 rounded-t-[32px]">
            <div className="flex items-center gap-3">
              <div
                className="
                  p-2.5 rounded-xl bg-zinc-100 dark:bg-white shadow-lg shadow-black/20"
              >
                <Bot className="w-5 h-5 text-zinc-900" />
              </div>

              <div className="flex-1">
                <h2 className="font-bold text-zinc-900 dark:text-white text-lg">
                  Agent-P
                </h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Autonomous Browser Agent
                </p>
              </div>

              {/* Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="
                  p-2.5 rounded-xl
                  dark:bg-zinc-800 bg-zinc-100
                  dark:hover:bg-zinc-700 hover:bg-zinc-200
                  dark:text-zinc-400 text-zinc-600
                  hover:text-amber-400
                  transition-all duration-300
                  hover:scale-110 active:scale-95
                  border dark:border-zinc-700/50 border-zinc-300
                "
                title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* INITIAL STATE */}
          {!isInitialized ? (
            <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-8">

              <div className="w-full max-w-md mt-10 space-y-4">

                <div
                  className="rounded-2xl border-2 border-zinc-300 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50 p-4"
                >
                  <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-2 font-medium">
                    Website URL
                  </label>
                  <input
                    type="url"
                    value={url}
                    placeholder="https://example.com"
                    className="
                      w-full
                      bg-transparent
                      text-zinc-900 dark:text-white
                      placeholder:text-zinc-400 dark:placeholder:text-zinc-500
                      outline-none
                    "
                    onChange={(e) => setUrl(e.target.value)}
                  />
                </div>

                <div
                  className="
                    rounded-2xl
                    border-2 border-zinc-300 dark:border-zinc-800
                    bg-zinc-50 dark:bg-zinc-800/50
                    p-4
                  "
                >
                  <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-2 font-medium">
                    Upload File
                  </label>

                  <input
                    type="file"
                    className="
                      w-full
                      text-sm
                      text-zinc-900 dark:text-white
                      file:border-0
                      file:rounded-xl
                      file:px-4
                      file:py-2
                      file:bg-zinc-200 dark:file:bg-zinc-700
                      file:text-zinc-900 dark:file:text-white
                      file:cursor-pointer
                      hover:file:bg-zinc-300 dark:hover:file:bg-zinc-600
                      file:transition-colors
                    "
                    accept='.pdf'
                    onChange={(e) => setResume(e.target.files?.[0] || null)}
                  />
                </div>
                <button
                  className="
                    w-full px-8 py-4 rounded-2xl bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 font-semibold hover:bg-zinc-800 dark:hover:bg-zinc-100 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 shadow-lg shadow-black/25 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 mt-4"

                  onClick={handleInitializeAgent}
                  disabled={!url || !resume || isUploading}
                >
                  {isUploading ? <div className="w-5 h-5 border-2 border-white dark:border-zinc-900 border-t-transparent dark:border-t-transparent rounded-full animate-spin mx-auto" /> : 'Initialize Agent'}
                </button>
              </div>
            </div>
          ) : (
            /* CHAT STATE */
            <div className="relative z-10 flex-1 flex flex-col min-h-0">

              {/* Messages */}
              <div className="
                flex-1 overflow-y-auto p-6 space-y-4
                [scrollbar-width:thin]
                [scrollbar-color:rgba(255,255,255,0.15)_transparent]
              ">
                {messages.map((msg) => {
                  if (msg.sender === 'system') {
                    return (
                      <div key={msg.id} className="flex justify-center my-2">
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-200/50 dark:bg-zinc-800/40 border border-zinc-300 dark:border-zinc-700/30 text-xs text-zinc-600 dark:text-zinc-400">
                          <span className={`${msg.text.startsWith('Ignored') ? 'text-red-500 dark:text-red-300' : 'text-emerald-600 dark:text-emerald-500'}`}>✦</span>
                          {msg.text}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${msg.sender === 'user' ?
                        'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 rounded-tr-sm'
                        : 'bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700/50 text-zinc-800 dark:text-zinc-200 rounded-tl-sm shadow-sm'
                        }`}>
                        {msg.text}
                      </div>
                    </div>
                  )
                })}
                <div ref={chatEndRef} />
              </div>

              {/* Input */}
              {!isExecutionComplete && <div className="p-5">
                <form
                  onSubmit={handleSendChatMessage}
                  className="
                    flex items-center gap-3
                    rounded-2xl
                    border-2 border-zinc-300 dark:border-zinc-800
                    bg-zinc-50 dark:bg-zinc-800/50
                    px-4 py-3
                    focus-within:border-zinc-500 dark:focus-within:border-zinc-600 transition-colors
                    shadow-sm
                  "
                >
                  <input
                    value={chatInput}
                    disabled={agentState.isProcessing}
                    onChange={(e) => setChatInput(e.currentTarget.value)}
                    placeholder="Tell Agent-P what to do..."
                    className="
                      flex-1
                      bg-transparent
                      text-zinc-900 dark:text-white
                      placeholder:text-zinc-400 dark:placeholder:text-zinc-500
                      outline-none
                    "
                  />

                  {agentState.isProcessing ? (
                    <button
                      type="button"
                      onClick={handleStopExecution}
                      className="
                      p-3 rounded-xl
                      bg-cyan-500 dark:bg-cyan-400 text-white
                      hover:bg-cyan-600 dark:hover:bg-cyan-300
                      hover:scale-105 active:scale-95
                    "
                    >
                      <CircleStop className="w-4 h-4" />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!chatInput.trim()}
                      className="
                      p-3 rounded-xl
                      bg-zinc-900 text-white dark:bg-white dark:text-zinc-900
                      hover:bg-zinc-800 dark:hover:bg-zinc-200
                      hover:scale-105 active:scale-95
                      transition-all dark:shadow-[0_0_20px_rgba(255,255,255,0.2)] shadow-[0_0_20px_rgba(0,0,0,0.1)]
                      disabled:opacity-50 disabled:hover:scale-100 disabled:shadow-none
                    "
                    >
                      <SendHorizonalIcon className="w-4 h-4" />
                    </button>
                  )}
                </form>
              </div>}
            </div>
          )}
        </div>
      </div>

      {/* RIGHT PANE */}
      <div className="w-[65%]">
        <div
          className="
            relative h-full overflow-hidden
            rounded-[32px]
            border-2 border-zinc-400 dark:border-zinc-800/80
            bg-white dark:bg-zinc-900
            shadow-xl shadow-zinc-300/50 dark:shadow-2xl dark:shadow-black/40
            flex flex-col
          "
        >
          {/* Subtle ambient glow */}
          <div className="absolute inset-0">
            <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-zinc-700/8 rounded-full blur-[180px]" />
            <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-zinc-600/8 rounded-full blur-[180px]" />
          </div>

          {/* Progress Section */}
          <div className="relative z-10 p-4 border-b border-zinc-800/80 shrink-0">
            <div
              className="
                rounded-2xl
                p-4
                bg-zinc-50 dark:bg-zinc-800
                border-2 border-zinc-300 dark:border-zinc-700/50
                shadow-md shadow-zinc-200/50 dark:shadow-xl dark:shadow-black/20
              "
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-zinc-500 dark:text-zinc-400 text-xs">
                    Current Task
                  </p>

                  <h2 className="text-lg font-bold text-zinc-900 dark:text-white">
                    {isInitialized ? 'Filling Application Form' : "Awaiting Parameters"}
                  </h2>
                </div>

                <div className="text-right">
                  <p className="text-zinc-500 dark:text-zinc-400 text-xs">
                    Progress
                  </p>

                  <h1 className="text-3xl font-black text-zinc-900 dark:text-white">
                    {progressPercentage}%
                  </h1>
                </div>
              </div>
              <div className="mt-3">
                <div className="h-2 rounded-full bg-zinc-300 dark:bg-zinc-700 overflow-hidden border border-zinc-200 dark:border-zinc-700/50">
                  <div
                    className="
                      h-full
                      w-[74%]
                      rounded-full
                      bg-zinc-900 dark:bg-white
                      transition-all duration-700 ease-out
                    "
                    style={{ width: `${progressPercentage}%` }}
                  />
                </div>
              </div>
            </div>

          </div>

          {/* Browser Area */}
          <div className="relative z-10 p-4 flex-1 min-h-0">
            <div
              className="
                h-full
                rounded-[28px]
                border-2 border-zinc-300 dark:border-zinc-800
                overflow-hidden
                bg-zinc-50 dark:bg-zinc-950
                shadow-inner
                flex flex-col
              "
            >
              {/* Browser Top Bar */}
              <div
                className="
                  h-14
                  px-5
                  flex items-center gap-3
                  border-b-2 border-zinc-400 dark:border-zinc-800
                  bg-gradient-to-r from-zinc-100 to-zinc-300 dark:from-zinc-800 dark:to-zinc-950
                  shrink-0
                "
              >
                <div className="w-3 h-3 rounded-full bg-zinc-300 dark:bg-zinc-600 hover:bg-red-400 transition-colors" />
                <div className="w-3 h-3 rounded-full bg-zinc-300 dark:bg-zinc-600 hover:bg-yellow-400 transition-colors" />
                <div className="w-3 h-3 rounded-full bg-zinc-300 dark:bg-zinc-600 hover:bg-green-400 transition-colors" />
                <div
                  className="
                    flex-1
                    h-9
                    rounded-full
                    border-2 border-zinc-400 dark:border-zinc-700/50
                    bg-zinc-50 dark:bg-zinc-800
                    flex items-center px-4
                    text-sm text-zinc-600 dark:text-zinc-400
                    truncate
                  "
                >
                  {url || 'https://target-form.com'}
                </div>
                <div
                  className="
                    px-4 py-1.5
                    rounded-full
                    bg-emerald-500/15
                    border border-emerald-500/25
                    text-emerald-400
                    text-xs
                    font-medium
                    flex items-center gap-2
                  "
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  LIVE
                </div>
              </div>

              {/* Website Stream */}
              <div className="relative h-[calc(100%-56px)]">

                {url ? (
                  liveImage ? (
                    <img
                      src={liveImage}
                      alt="Live Agent View"
                      className="w-full h-full object-cover object-top scale-[1.03] transition-transform duration-500 origin-top"
                    />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-zinc-500 dark:text-zinc-600">
                      {(isInitialized || isUploading) ? (
                        <AgentLoadingAnimation />
                      ) : (
                        <>
                          <Bot className="w-12 h-12 mb-4 opacity-50 text-zinc-400 dark:text-zinc-600" />
                          Provide a URL to preview the target form.
                        </>
                      )}
                    </div>
                  )
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 text-zinc-500 dark:text-zinc-600">
                    Provide a URL to preview the target form.
                  </div>
                )}
                {/* Floating Status */}
                {isInitialized && (
                  <div
                    className="
                      absolute top-4 right-4
                      px-4 py-2
                      rounded-full
                      border border-emerald-500/25
                      bg-white/90 dark:bg-zinc-900/90
                      backdrop-blur-xl
                      text-emerald-600 dark:text-emerald-400
                      text-xs
                      font-medium
                    "
                  >

                    Agent is mapping DOM elements.
                  </div>
                )}
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Pilot() {
  return (
    <ToastProvider>
      <PilotContent />
    </ToastProvider>
  );
}