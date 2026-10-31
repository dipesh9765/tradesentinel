// Speech Synthesis (TTS) & Web Speech Recognition (STT) Service

export type VoiceCommand = "APPROVE" | "REJECT" | "SCAN" | "MUTE" | "UNKNOWN";

class SpeechService {
  private synth: SpeechSynthesis | null = null;
  private recognition: any = null;
  private isListening: boolean = false;
  private isMuted: boolean = false;
  private commandCallback: ((cmd: VoiceCommand, rawText: string) => void) | null = null;
  private transcriptCallback: ((transcript: string) => void) | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      this.synth = window.speechSynthesis;
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

      if (SpeechRecognition) {
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = "en-IN"; // Supports Indian English accent natively

        this.recognition.onresult = (event: any) => {
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.toLowerCase().trim();
            
            if (this.transcriptCallback) {
              this.transcriptCallback(transcript);
            }

            if (event.results[i].isFinal) {
              this.parseVoiceCommand(transcript);
            }
          }
        };

        this.recognition.onerror = (event: any) => {
          console.warn("Speech recognition error:", event.error);
        };

        this.recognition.onend = () => {
          // Restart recognition automatically if still marked as listening
          if (this.isListening) {
            try {
              this.recognition.start();
            } catch {
              // Ignore already running errors
            }
          }
        };
      }
    }
  }

  setMuted(muted: boolean) {
    this.isMuted = muted;
    if (muted && this.synth) {
      this.synth.cancel();
    }
  }

  getMuted(): boolean {
    return this.isMuted;
  }

  speak(text: string, onEnd?: () => void) {
    if (this.isMuted || !this.synth) {
      if (onEnd) onEnd();
      return;
    }

    this.synth.cancel(); // Cancel any ongoing speech
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Pick natural voice if available
    const voices = this.synth.getVoices();
    const naturalVoice = voices.find(
      (v) => (v.lang.includes("en-IN") || v.lang.includes("en-US")) && !v.name.includes("whisper")
    );
    if (naturalVoice) {
      utterance.voice = naturalVoice;
    }

    utterance.onend = () => {
      if (onEnd) onEnd();
    };

    utterance.onerror = () => {
      if (onEnd) onEnd();
    };

    this.synth.speak(utterance);
  }

  startListening(
    onCommand: (cmd: VoiceCommand, rawText: string) => void,
    onTranscript?: (text: string) => void
  ) {
    this.commandCallback = onCommand;
    if (onTranscript) this.transcriptCallback = onTranscript;
    this.isListening = true;

    if (this.recognition) {
      try {
        this.recognition.start();
      } catch {
        // Recognition might already be running
      }
    }
  }

  stopListening() {
    this.isListening = false;
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {
        // Ignore
      }
    }
  }

  getIsListening(): boolean {
    return this.isListening;
  }

  private parseVoiceCommand(text: string) {
    console.log("Parsing voice input:", text);
    let cmd: VoiceCommand = "UNKNOWN";

    if (
      text.includes("approve") ||
      text.includes("confirm") ||
      text.includes("yes") ||
      text.includes("execute") ||
      text.includes("take trade") ||
      text.includes("buy it")
    ) {
      cmd = "APPROVE";
    } else if (
      text.includes("reject") ||
      text.includes("cancel") ||
      text.includes("no") ||
      text.includes("pass") ||
      text.includes("skip") ||
      text.includes("decline")
    ) {
      cmd = "REJECT";
    } else if (
      text.includes("scan") ||
      text.includes("analyze") ||
      text.includes("check")
    ) {
      cmd = "SCAN";
    }

    if (this.commandCallback) {
      this.commandCallback(cmd, text);
    }
  }
}

export const speechService = new SpeechService();
