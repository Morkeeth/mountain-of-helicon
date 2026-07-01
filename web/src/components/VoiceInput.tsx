import { useState, useRef, useEffect } from 'react';

interface Props {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

export function VoiceInput({ onTranscript, disabled }: Props) {
  const [recording, setRecording] = useState(false);
  const [supported, setSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    setSupported(!!SR);
    if (SR) {
      const recognition = new SR();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const text = event.results[0][0].transcript;
        onTranscript(text);
        setRecording(false);
      };
      recognition.onerror = () => setRecording(false);
      recognition.onend = () => setRecording(false);
      recognitionRef.current = recognition;
    }
  }, [onTranscript]);

  const toggle = () => {
    if (!recognitionRef.current) return;
    if (recording) {
      recognitionRef.current.stop();
      setRecording(false);
    } else {
      recognitionRef.current.start();
      setRecording(true);
    }
  };

  if (!supported) return null;

  return (
    <button
      onClick={toggle}
      disabled={disabled}
      className={`text-[11px] px-2 py-1.5 rounded-md transition-colors ${
        recording
          ? 'text-red-500 bg-red-50 animate-pulse border border-red-200'
          : 'text-zinc-500 hover:text-zinc-400 hover:bg-zinc-900/50'
      } disabled:opacity-30`}
      title={recording ? 'Stop' : 'Voice'}
    >
      {recording ? 'rec' : 'mic'}
    </button>
  );
}
