import { useState, useEffect, useRef, useCallback } from "react";

/**
 * useSpeech — browser-native Speech-to-Text via Web Speech API.
 * Recognized text is returned incrementally so it can be appended to input.
 *
 * @param {function} onResult  — called with (transcript: string) on each final result
 * @param {function} onInterim — called with (transcript: string) on interim results (optional)
 */
export function useSpeech({ onResult, onInterim } = {}) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [error, setError] = useState(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setIsSupported(false);
      return;
    }

    setIsSupported(true);

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;       // stop after one utterance
    recognition.interimResults = true;    // stream partial results

    recognition.onstart = () => {
      setIsListening(true);
      setError(null);
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += text;
        } else {
          interimTranscript += text;
        }
      }

      if (interimTranscript && onInterim) {
        onInterim(interimTranscript);
      }
      if (finalTranscript && onResult) {
        onResult(finalTranscript.trim());
      }
    };

    recognition.onerror = (event) => {
      const msg =
        event.error === "not-allowed"
          ? "Microphone access denied. Please allow mic permissions."
          : event.error === "no-speech"
          ? "No speech detected. Try again."
          : `Speech error: ${event.error}`;
      setError(msg);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.abort();
    };
  }, []); // eslint-disable-line

  const startListening = useCallback(() => {
    if (!recognitionRef.current || isListening) return;
    setError(null);
    try {
      recognitionRef.current.start();
    } catch {
      // already started — ignore
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current || !isListening) return;
    recognitionRef.current.stop();
  }, [isListening]);

  const toggleListening = useCallback(() => {
    isListening ? stopListening() : startListening();
  }, [isListening, startListening, stopListening]);

  return { isListening, isSupported, error, startListening, stopListening, toggleListening };
}
