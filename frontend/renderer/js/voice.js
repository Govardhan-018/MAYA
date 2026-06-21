// ═══════════════════════════════════════════════════════════
// voice.js — Push-to-Talk, MediaRecorder, TTS
// ═══════════════════════════════════════════════════════════

const MAYAVoice = (() => {
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let activateSound = null;
  let deactivateSound = null;

  // ─── Initialize ────────────────────────────────────────
  function init() {
    // Preload sounds
    activateSound = new Audio('../assets/sounds/activate.mp3');
    deactivateSound = new Audio('../assets/sounds/deactivate.mp3');
    activateSound.volume = 0.3;
    deactivateSound.volume = 0.3;

    // Mic button
    const micBtn = document.getElementById('btn-mic');
    if (micBtn) {
      micBtn.addEventListener('mousedown', startRecording);
      micBtn.addEventListener('mouseup', stopRecording);
      micBtn.addEventListener('mouseleave', () => {
        if (isRecording) stopRecording();
      });

      // Touch support
      micBtn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        startRecording();
      });
      micBtn.addEventListener('touchend', (e) => {
        e.preventDefault();
        stopRecording();
      });
    }

    // Listen for tray toggle voice event
    if (window.maya && window.maya.onTrayToggleVoice) {
      window.maya.onTrayToggleVoice(() => {
        toggleVoice();
      });
    }
  }

  // ─── Start Recording ──────────────────────────────────
  async function startRecording() {
    if (isRecording) return;
    if (!MAYAState.voiceReady && !MAYAState.settings.voiceEnabled) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm'
      });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach(t => t.stop());

        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        audioChunks = [];

        // Transcribe
        await transcribeAndSend(audioBlob);
      };

      mediaRecorder.start();
      isRecording = true;

      // Update UI
      const micBtn = document.getElementById('btn-mic');
      if (micBtn) micBtn.classList.add('recording');

      MAYAApp.updateState({ isRecording: true });

      // Play activate sound
      playSound(activateSound);

    } catch (err) {
      console.warn('[MAYA Voice] Microphone access denied:', err.message);
      MAYAChat.appendMessage('error', 'Microphone access denied. Check browser permissions.');
    }
  }

  // ─── Stop Recording ───────────────────────────────────
  function stopRecording() {
    if (!isRecording || !mediaRecorder) return;

    mediaRecorder.stop();
    isRecording = false;

    // Update UI
    const micBtn = document.getElementById('btn-mic');
    if (micBtn) micBtn.classList.remove('recording');

    MAYAApp.updateState({ isRecording: false });

    // Play deactivate sound
    playSound(deactivateSound);
  }

  // ─── Transcribe & Send ────────────────────────────────
  async function transcribeAndSend(audioBlob) {
    try {
      const data = await MAYAAPI.transcribeVoice(audioBlob);
      if (data && data.text && data.text.trim()) {
        MAYAChat.injectAndSend(data.text.trim());
      } else {
        MAYAChat.appendMessage('error', 'Could not transcribe audio. Try again.');
      }
    } catch (err) {
      MAYAChat.appendMessage('error', `Transcription failed: ${err.message}`);
    }
  }

  // ─── Toggle Voice ─────────────────────────────────────
  function toggleVoice() {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  // ─── Play Sound ───────────────────────────────────────
  function playSound(audio) {
    if (!audio) return;
    try {
      audio.currentTime = 0;
      audio.play().catch(() => {
        // Ignore autoplay restrictions
      });
    } catch (e) {
      // Ignore
    }
  }

  // ─── Public API ───────────────────────────────────────
  return {
    init,
    startRecording,
    stopRecording,
    toggleVoice,
    isRecording: () => isRecording
  };
})();
