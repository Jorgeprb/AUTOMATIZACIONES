import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Mic2,
  Pause,
  Play,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  Volume2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import {
  closeRealtimePreviewSession,
  closeRealtimePreviewSessionKeepalive,
  createRealtimePreviewSession,
  heartbeatRealtimePreviewSession,
  listVoiceProviderVoices,
  previewAssistantVoice,
  sendRealtimePreviewToolCall,
} from "@/api/assistants";
import { FormSection } from "@/components/common/FormSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  applyAssistantTemplate,
  applyVoicePreset,
  assistantConfigDefaults,
  assistantConfigFormSchema,
  assistantTemplateNames,
  voicePresetNames,
  type AssistantConfigFormValues,
  type AssistantConfigPayload,
  type AssistantTemplateName,
  type VoicePresetName,
} from "@/schemas/assistant";
import type { AssistantOptions } from "@/schemas/domain";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

type AssistantConfigTab =
  | "settings"
  | "conversation"
  | "prompt"
  | "booking"
  | "safety"
  | "advanced"
  | "preview";

const assistantConfigTabs: Array<{
  id: AssistantConfigTab;
  label: string;
  help: string;
}> = [
  { id: "settings", label: "Ajustes", help: "Básico, modelo y voz" },
  { id: "conversation", label: "Comportamiento", help: "Naturalidad y control" },
  { id: "prompt", label: "Prompt", help: "Prompt general" },
  { id: "booking", label: "Reservas", help: "Datos y agenda" },
  { id: "safety", label: "Seguridad", help: "Límites médicos" },
  { id: "advanced", label: "Avanzado", help: "Mensajes y privacidad" },
  { id: "preview", label: "Preview", help: "Vista final" },
];

type RealtimePreviewStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "speaking"
  | "interrupted"
  | "error"
  | "closed";

function speechSpeedToNumber(value: AssistantConfigFormValues["speech_speed"]) {
  if (value === "slow") return "0.85";
  if (value === "fast") return "1.15";
  return "1";
}

function speechSpeedFromNumber(value: number): AssistantConfigFormValues["speech_speed"] {
  if (value <= 0.9) return "slow";
  if (value >= 1.1) return "fast";
  return "normal";
}

function pauseStyleToNumber(value: AssistantConfigFormValues["pause_style"]) {
  if (value === "short") return "0.7";
  if (value === "slow") return "1.4";
  return "1";
}

function pauseStyleFromNumber(value: number): AssistantConfigFormValues["pause_style"] {
  if (value <= 0.85) return "short";
  if (value >= 1.2) return "slow";
  return "natural";
}

function buildConfigPayload(values: AssistantConfigFormValues): AssistantConfigPayload {
  const externalVoice = values.voice_provider !== "openai";
  return {
    ...values,
    call_audio_mode: externalVoice ? "vps_media_bridge" : values.call_audio_mode,
    temperature: values.temperature || null,
    idle_timeout_ms: values.idle_timeout_ms ? Number(values.idle_timeout_ms) : null,
    tts_model: values.tts_model.trim() || null,
    voice_id: values.voice_id.trim() || null,
    voice_locale: values.voice_locale.trim() || null,
    voice_gender: values.voice_gender.trim() || null,
    azure_speech_region: values.azure_speech_region.trim() || null,
    voice_style: values.voice_style.trim() || null,
    voice_stability: values.voice_stability || null,
    voice_similarity: values.voice_similarity || null,
    voice_temperature: values.voice_temperature || null,
  };
}

export function AssistantConfigForm({
  clinicId,
  assistantConfigId,
  options,
  defaultValues = assistantConfigDefaults,
  contextWarnings = [],
  onSubmit,
  onCancel,
  isPending,
}: {
  clinicId: string;
  assistantConfigId?: string | null;
  options: AssistantOptions;
  defaultValues?: AssistantConfigFormValues;
  contextWarnings?: string[];
  onSubmit: (values: AssistantConfigFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AssistantConfigFormValues>({
    resolver: zodResolver(assistantConfigFormSchema),
    defaultValues,
  });
  const firstMessage = watch("first_message");
  const systemPrompt = watch("system_prompt");
  const realtimeVoice = watch("realtime_voice");
  const realtimeModel = watch("realtime_model");
  const callAudioMode = watch("call_audio_mode");
  const voiceProvider = watch("voice_provider");
  const externalVoiceLegalConfirmed = watch("external_voice_legal_confirmed");
  const ttsPreviewVoice = watch("tts_preview_voice");
  const fallbackVoice = watch("fallback_voice");
  const ttsModel = watch("tts_model");
  const voiceId = watch("voice_id");
  const voiceLocale = watch("voice_locale");
  const azureSpeechRegion = watch("azure_speech_region");
  const voiceStyle = watch("voice_style");
  const voiceSpeed = watch("voice_speed");
  const voicePitch = watch("voice_pitch");
  const voiceStability = watch("voice_stability");
  const voiceSimilarity = watch("voice_similarity");
  const voiceTemperature = watch("voice_temperature");
  const telephonyCodec = watch("telephony_codec");
  const voicePreset = watch("voice_preset");
  const voiceInstructions = watch("voice_instructions");
  const speechSpeed = watch("speech_speed");
  const pauseStyle = watch("pause_style");
  const phoneReadingStyle = watch("phone_reading_style");
  const dateReadingStyle = watch("date_reading_style");
  const priceReadingStyle = watch("price_reading_style");
  const allowInterruptions = watch("allow_interruptions");
  const idleTimeoutMs = watch("idle_timeout_ms");
  const aiDisclosureEnabled = watch("ai_disclosure_enabled");
  const aiDisclosureMessage = watch("ai_disclosure_message");
  const previewAudioFormat = watch("preview_audio_format");
  const usesExternalVoiceProvider = voiceProvider !== "openai";
  const providerOptions =
    options.voice_providers?.length > 0
      ? options.voice_providers
      : [
          {
            id: "openai",
            display_name: "OpenAI",
            configured: true,
            supports_tts: true,
            supports_streaming: true,
            supports_telephony_codec: false,
            supports_stt: false,
            supports_voice_clone: false,
            requires_consent: false,
            recommended: true,
            enabled: true,
            notes: null,
          },
        ];
  const selectedVoiceProvider = providerOptions.find(
    (provider) => provider.id === voiceProvider,
  );
  const providerVoicesQuery = useQuery({
    queryKey: ["voice-provider-voices", voiceProvider],
    queryFn: () => listVoiceProviderVoices(voiceProvider),
    enabled: Boolean(voiceProvider),
    staleTime: 1000 * 60 * 10,
  });
  const providerVoices = providerVoicesQuery.data ?? [];
  const providerVoiceChoices =
    voiceProvider === "openai"
      ? options.voices.map((voice) => ({
          id: voice.id,
          label: voice.label,
          model: realtimeModel,
          locale: "multi",
          recommended: voice.recommended,
        }))
      : providerVoices.map((voice) => ({
          id: voice.voice_id,
          label: `${voice.display_name}${voice.locale ? ` · ${voice.locale}` : ""}`,
          model: voice.model,
          locale: voice.locale,
          recommended: voice.recommended,
        }));
  const providerModelChoices = Array.from(
    new Set(providerVoiceChoices.map((voice) => voice.model).filter(Boolean)),
  );
  const outputAudioFormats =
    options.output_audio_formats?.length > 0
      ? options.output_audio_formats
      : ["pcm16", "wav", "mp3", "opus"];
  const telephonyCodecs =
    options.telephony_codecs?.length > 0
      ? options.telephony_codecs
      : ["pcmu", "pcma", "pcm16"];
  const requiresLegalConfirmation = [
    "elevenlabs",
    "resemble",
    "local_coqui",
    "local_chatterbox",
    "custom_http",
  ].includes(voiceProvider);
  const maxPromptLength = 12000;
  const [activeTab, setActiveTab] = useState<AssistantConfigTab>("settings");
  const [voicePreviewText, setVoicePreviewText] = useState(
    "Hola, soy el asistente virtual. ¿En qué puedo ayudarle?",
  );
  const [voicePreviewStatus, setVoicePreviewStatus] = useState<
    "idle" | "generating" | "playing" | "paused"
  >("idle");
  const [voicePreviewError, setVoicePreviewError] = useState("");
  const [comparisonVoices, setComparisonVoices] = useState<string[]>([]);
  const [voiceSamples, setVoiceSamples] = useState<
    Array<{ voice: string; url: string }>
  >([]);
  const [realtimeStatus, setRealtimeStatus] =
    useState<RealtimePreviewStatus>("idle");
  const [realtimeError, setRealtimeError] = useState("");
  const [realtimeSessionId, setRealtimeSessionId] = useState<string | null>(null);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceAudioUrlRef = useRef<string | null>(null);
  const voiceSampleUrlsRef = useRef<string[]>([]);
  const voiceAbortRef = useRef<AbortController | null>(null);
  const realtimePeerRef = useRef<RTCPeerConnection | null>(null);
  const realtimeDataChannelRef = useRef<RTCDataChannel | null>(null);
  const realtimeStreamRef = useRef<MediaStream | null>(null);
  const realtimeAudioRef = useRef<HTMLAudioElement | null>(null);
  const realtimeSessionIdRef = useRef<string | null>(null);
  const realtimeHeartbeatRef = useRef<number | null>(null);
  const realtimeExternalTtsRef = useRef(false);
  const realtimeTextBufferRef = useRef("");
  const checklist = [
    {
      label: "Trabajadores activos",
      ok: !contextWarnings.includes("No hay trabajadores activos."),
      help: "Crea al menos un trabajador activo.",
    },
    {
      label: "Servicios reservables",
      ok: !contextWarnings.some((warning) =>
        warning.includes("No hay servicios reservables"),
      ),
      help: "Activa servicios reservables por bot.",
    },
    {
      label: "Calendario conectado",
      ok: !contextWarnings.includes("No hay calendario conectado."),
      help: "Conecta Google Calendar y enlaza calendarios.",
    },
    {
      label: "Número configurado",
      ok: !contextWarnings.includes("No hay número configurado."),
      help: "Añade un número activo para la clínica.",
    },
    {
      label: "Prompt suficiente",
      ok: systemPrompt.trim().length >= 40 && systemPrompt.length <= maxPromptLength,
      help: "Escribe un prompt claro, ni vacío ni enorme.",
    },
  ];

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  useEffect(() => {
    if (usesExternalVoiceProvider && callAudioMode !== "vps_media_bridge") {
      setValue("call_audio_mode", "vps_media_bridge", {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }, [callAudioMode, setValue, usesExternalVoiceProvider]);

  const applySabelaVoice = useCallback(() => {
    setValue("voice_provider", "azure", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("call_audio_mode", "vps_media_bridge", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("tts_model", "azure-neural", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("voice_id", "gl-ES-SabelaNeural", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("tts_preview_voice", "gl-ES-SabelaNeural", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("voice_locale", "gl-ES", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("language", "gl-ES", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("telephony_codec", "pcma", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("output_audio_format", "wav", {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue("voice_style", "", {
      shouldDirty: true,
      shouldValidate: true,
    });
    toast.success("Sabela lista: Azure, gallego y VPS Media Bridge.");
  }, [setValue]);

  const clearVoiceSamples = useCallback(() => {
    for (const url of voiceSampleUrlsRef.current) URL.revokeObjectURL(url);
    voiceSampleUrlsRef.current = [];
    setVoiceSamples([]);
  }, []);

  const buildVoicePreviewPayload = useCallback(
    (voiceOverride?: string, textOverride?: string) => ({
      text: (textOverride ?? voicePreviewText).trim(),
      realtime_voice: realtimeVoice,
      realtime_model: realtimeModel,
      call_audio_mode: usesExternalVoiceProvider
        ? "vps_media_bridge"
        : callAudioMode,
      voice_provider: voiceProvider,
      tts_model: getValues().tts_model.trim() || null,
      voice_id: getValues().voice_id.trim() || null,
      voice_locale: getValues().voice_locale.trim() || null,
      voice_gender: getValues().voice_gender.trim() || null,
      azure_speech_region: getValues().azure_speech_region.trim() || null,
      voice_style: getValues().voice_style.trim() || null,
      voice_speed: getValues().voice_speed,
      voice_pitch: getValues().voice_pitch,
      voice_stability: getValues().voice_stability || null,
      voice_similarity: getValues().voice_similarity || null,
      voice_temperature: getValues().voice_temperature || null,
      output_audio_format: getValues().output_audio_format,
      telephony_codec: getValues().telephony_codec,
      external_voice_legal_confirmed: getValues().external_voice_legal_confirmed,
      tts_preview_voice: (voiceOverride ?? ttsPreviewVoice) || null,
      fallback_voice: fallbackVoice || null,
      voice_preset: voicePreset || null,
      voice_instructions: voiceInstructions || null,
      speech_speed: speechSpeed,
      pause_style: pauseStyle,
      phone_reading_style: phoneReadingStyle,
      date_reading_style: dateReadingStyle,
      price_reading_style: priceReadingStyle,
      allow_interruptions: allowInterruptions,
      idle_timeout_ms: idleTimeoutMs ? Number(idleTimeoutMs) : null,
      ai_disclosure_enabled: aiDisclosureEnabled,
      ai_disclosure_message: aiDisclosureMessage || null,
      preview_audio_format: previewAudioFormat,
    }),
    [
      aiDisclosureEnabled,
      aiDisclosureMessage,
      callAudioMode,
      allowInterruptions,
      dateReadingStyle,
      fallbackVoice,
      getValues,
      idleTimeoutMs,
      pauseStyle,
      phoneReadingStyle,
      previewAudioFormat,
      priceReadingStyle,
      realtimeModel,
      realtimeVoice,
      speechSpeed,
      ttsPreviewVoice,
      usesExternalVoiceProvider,
      voiceProvider,
      azureSpeechRegion,
      voiceStyle,
      voiceInstructions,
      voicePreset,
      voicePreviewText,
    ],
  );

  const stopVoicePreview = useCallback(() => {
    voiceAbortRef.current?.abort();
    voiceAbortRef.current = null;
    voiceAudioRef.current?.pause();
    voiceAudioRef.current = null;
    if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
    voiceAudioUrlRef.current = null;
    clearVoiceSamples();
    setVoicePreviewStatus("idle");
  }, [clearVoiceSamples]);

  useEffect(() => stopVoicePreview, [stopVoicePreview]);

  const stopRealtimePreview = useCallback(
    (reason = "closed_by_browser") => {
      const sessionId = realtimeSessionIdRef.current;
      if (realtimeHeartbeatRef.current !== null) {
        window.clearInterval(realtimeHeartbeatRef.current);
        realtimeHeartbeatRef.current = null;
      }
      realtimeDataChannelRef.current?.close();
      realtimeDataChannelRef.current = null;
      realtimePeerRef.current?.getSenders().forEach((sender) => {
        sender.track?.stop();
      });
      realtimePeerRef.current?.close();
      realtimePeerRef.current = null;
      realtimeStreamRef.current?.getTracks().forEach((track) => track.stop());
      realtimeStreamRef.current = null;
      realtimeAudioRef.current?.pause();
      realtimeAudioRef.current = null;
      voiceAbortRef.current?.abort();
      voiceAbortRef.current = null;
      voiceAudioRef.current?.pause();
      voiceAudioRef.current = null;
      if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
      voiceAudioUrlRef.current = null;
      realtimeExternalTtsRef.current = false;
      realtimeTextBufferRef.current = "";
      realtimeSessionIdRef.current = null;
      setRealtimeSessionId(null);
      if (sessionId) {
        if (reason === "page_unload") {
          closeRealtimePreviewSessionKeepalive(sessionId);
        } else {
          void closeRealtimePreviewSession(sessionId).catch(() => undefined);
        }
      }
      setRealtimeStatus("closed");
    },
    [],
  );

  useEffect(() => {
    const handleUnload = () => stopRealtimePreview("page_unload");
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      stopRealtimePreview("component_unmount");
    };
  }, [stopRealtimePreview]);

  const sendRealtimeToolOutput = useCallback(
    async (
      sessionId: string,
      dataChannel: RTCDataChannel,
      payload: { name: string; call_id: string; arguments: Record<string, unknown> },
    ) => {
      const result = await sendRealtimePreviewToolCall(sessionId, payload);
      dataChannel.send(
        JSON.stringify({
          type: "conversation.item.create",
          item: {
            type: "function_call_output",
            call_id: result.call_id,
            output: JSON.stringify(result.output),
          },
        }),
      );
      dataChannel.send(
        JSON.stringify({
          type: "response.create",
          ...(realtimeExternalTtsRef.current
            ? { response: { output_modalities: ["text"] } }
            : {}),
        }),
      );
    },
    [],
  );

  const synthesizeRealtimeExternalSpeech = useCallback(
    async (text: string) => {
      const cleanText = text.trim();
      if (!cleanText || !realtimeExternalTtsRef.current) return;
      voiceAbortRef.current?.abort();
      voiceAudioRef.current?.pause();
      if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
      voiceAudioRef.current = null;
      voiceAudioUrlRef.current = null;
      const controller = new AbortController();
      voiceAbortRef.current = controller;
      setRealtimeStatus("speaking");
      setVoicePreviewStatus("generating");
      try {
        const blob = await previewAssistantVoice(
          clinicId,
          buildVoicePreviewPayload(undefined, cleanText),
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => {
          setVoicePreviewStatus("idle");
          if (realtimeSessionIdRef.current) setRealtimeStatus("listening");
        };
        audio.onpause = () => {
          if (!audio.ended) setVoicePreviewStatus("paused");
        };
        voiceAudioUrlRef.current = url;
        voiceAudioRef.current = audio;
        await audio.play();
        setVoicePreviewStatus("playing");
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "No se pudo generar TTS externo.";
        setRealtimeError(message);
        setRealtimeStatus("error");
        setVoicePreviewStatus("idle");
      } finally {
        if (voiceAbortRef.current === controller) voiceAbortRef.current = null;
      }
    },
    [buildVoicePreviewPayload, clinicId],
  );

  const handleRealtimeEvent = useCallback(
    (event: MessageEvent<string>) => {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(event.data) as Record<string, unknown>;
      } catch {
        return;
      }
      const type = String(payload.type ?? "");
      if (type.includes("speech_started")) {
        if (voiceAudioRef.current && !voiceAudioRef.current.paused) {
          voiceAudioRef.current.pause();
          voiceAbortRef.current?.abort();
          setRealtimeStatus("interrupted");
        } else {
          setRealtimeStatus("listening");
        }
      }
      if (
        !realtimeExternalTtsRef.current &&
        (type.startsWith("response.audio") || type.includes("output_audio"))
      ) {
        setRealtimeStatus("speaking");
      }
      if (
        realtimeExternalTtsRef.current &&
        (type === "response.output_text.delta" ||
          type === "response.output_audio_transcript.delta")
      ) {
        realtimeTextBufferRef.current += String(payload.delta ?? "");
      }
      if (type === "response.done") {
        if (realtimeExternalTtsRef.current) {
          const text = realtimeTextBufferRef.current.trim();
          realtimeTextBufferRef.current = "";
          if (text) void synthesizeRealtimeExternalSpeech(text);
          else setRealtimeStatus("listening");
        } else {
          setRealtimeStatus("listening");
        }
      }
      if (type === "error") {
        setRealtimeError("OpenAI Realtime devolvió un error.");
        setRealtimeStatus("error");
      }
      if (type !== "response.function_call_arguments.done") return;
      const sessionId = realtimeSessionIdRef.current;
      const dataChannel = realtimeDataChannelRef.current;
      const name = String(payload.name ?? "");
      const callId = String(payload.call_id ?? "");
      const rawArguments = String(payload.arguments ?? "{}");
      if (!sessionId || !dataChannel || !name || !callId) return;
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(rawArguments) as Record<string, unknown>;
      } catch {
        args = {};
      }
      void sendRealtimeToolOutput(sessionId, dataChannel, {
        name,
        call_id: callId,
        arguments: args,
      }).catch((error: unknown) => {
        const message =
          error instanceof Error ? error.message : "La tool de prueba falló.";
        setRealtimeError(message);
        setRealtimeStatus("error");
      });
    },
    [sendRealtimeToolOutput, synthesizeRealtimeExternalSpeech],
  );

  const playVoiceAudio = useCallback(async (audio: HTMLAudioElement) => {
    try {
      await audio.play();
      setVoicePreviewStatus("playing");
    } catch {
      setVoicePreviewStatus("paused");
      setVoicePreviewError(
        "El navegador bloqueó la reproducción automática. Pulsa reproducir.",
      );
    }
  }, []);

  const handleListenVoice = useCallback(async () => {
    const text = voicePreviewText.trim();
    if (!text) {
      setVoicePreviewError("Escribe una frase para probar la voz.");
      return;
    }
    voiceAbortRef.current?.abort();
    voiceAudioRef.current?.pause();
    clearVoiceSamples();
    if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
    voiceAudioRef.current = null;
    voiceAudioUrlRef.current = null;
    const controller = new AbortController();
    voiceAbortRef.current = controller;
    setVoicePreviewStatus("generating");
    setVoicePreviewError("");
    try {
      const blob = await previewAssistantVoice(
        clinicId,
        buildVoicePreviewPayload(),
        controller.signal,
      );
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => setVoicePreviewStatus("idle");
      audio.onpause = () => {
        if (!audio.ended) setVoicePreviewStatus("paused");
      };
      voiceAudioUrlRef.current = url;
      voiceAudioRef.current = audio;
      await playVoiceAudio(audio);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      const message =
        error instanceof Error ? error.message : "No se pudo generar audio.";
      setVoicePreviewError(message);
      setVoicePreviewStatus("idle");
      toast.error(message);
    } finally {
      if (voiceAbortRef.current === controller) voiceAbortRef.current = null;
    }
  }, [
    buildVoicePreviewPayload,
    clearVoiceSamples,
    clinicId,
    playVoiceAudio,
    voicePreviewText,
  ]);

  const handleToggleVoiceAudio = useCallback(() => {
    const audio = voiceAudioRef.current;
    if (!audio) return;
    if (voicePreviewStatus === "playing") {
      audio.pause();
      return;
    }
    void playVoiceAudio(audio);
  }, [playVoiceAudio, voicePreviewStatus]);

  const handleRepeatVoiceAudio = useCallback(() => {
    const audio = voiceAudioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    void playVoiceAudio(audio);
  }, [playVoiceAudio]);

  const handleToggleRealtimePreview = useCallback(async () => {
    if (
      realtimeStatus === "connecting" ||
      realtimeStatus === "listening" ||
      realtimeStatus === "speaking" ||
      realtimeStatus === "interrupted"
    ) {
      stopRealtimePreview("button_stop");
      return;
    }
    stopVoicePreview();
    setRealtimeError("");
    setRealtimeStatus("connecting");
    try {
      const values = getValues();
      const preview = await createRealtimePreviewSession(clinicId, {
        assistant_config_id: assistantConfigId ?? null,
        config: buildConfigPayload(values),
      });
      realtimeSessionIdRef.current = preview.id;
      setRealtimeSessionId(preview.id);
      realtimeExternalTtsRef.current = preview.external_tts_required;
      realtimeTextBufferRef.current = "";
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      realtimeStreamRef.current = stream;
      const peer = new RTCPeerConnection();
      realtimePeerRef.current = peer;
      for (const track of stream.getTracks()) peer.addTrack(track, stream);
      const audio = new Audio();
      audio.autoplay = true;
      realtimeAudioRef.current = audio;
      peer.ontrack = (event) => {
        if (preview.external_tts_required) return;
        const [remoteStream] = event.streams;
        if (remoteStream) {
          audio.srcObject = remoteStream;
          void audio.play().catch(() => undefined);
        }
      };
      const dataChannel = peer.createDataChannel("oai-events");
      realtimeDataChannelRef.current = dataChannel;
      dataChannel.onmessage = handleRealtimeEvent;
      dataChannel.onopen = () => {
        dataChannel.send(
          JSON.stringify({
            type: "response.create",
            response: {
              instructions: preview.initial_message,
              ...(preview.external_tts_required ? { output_modalities: ["text"] } : {}),
            },
          }),
        );
        setRealtimeStatus("listening");
      };
      dataChannel.onerror = () => {
        setRealtimeError("Error en el canal Realtime.");
        setRealtimeStatus("error");
      };
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const answerResponse = await fetch(
        `https://api.openai.com/v1/realtime?model=${encodeURIComponent(preview.model)}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${preview.client_secret}`,
            "Content-Type": "application/sdp",
          },
          body: offer.sdp ?? "",
        },
      );
      if (!answerResponse.ok) {
        throw new Error("OpenAI no aceptó la conexión WebRTC de prueba.");
      }
      const answer = await answerResponse.text();
      await peer.setRemoteDescription({ type: "answer", sdp: answer });
      realtimeHeartbeatRef.current = window.setInterval(() => {
        const sessionId = realtimeSessionIdRef.current;
        if (!sessionId) return;
        void heartbeatRealtimePreviewSession(sessionId).catch(() => {
          stopRealtimePreview("heartbeat_failed");
          setRealtimeError("La sesión de prueba expiró.");
          setRealtimeStatus("error");
        });
      }, 25_000);
    } catch (error) {
      stopRealtimePreview("start_failed");
      const message =
        error instanceof Error
          ? error.message
          : "No se pudo abrir la prueba Realtime.";
      setRealtimeError(message);
      setRealtimeStatus("error");
      toast.error(message);
    }
  }, [
    assistantConfigId,
    clinicId,
    getValues,
    handleRealtimeEvent,
    realtimeStatus,
    stopRealtimePreview,
    stopVoicePreview,
  ]);

  const handlePlaySample = useCallback(
    (url: string) => {
      voiceAudioRef.current?.pause();
      voiceAudioUrlRef.current = null;
      const audio = new Audio(url);
      audio.onended = () => setVoicePreviewStatus("idle");
      audio.onpause = () => {
        if (!audio.ended) setVoicePreviewStatus("paused");
      };
      voiceAudioRef.current = audio;
      void playVoiceAudio(audio);
    },
    [playVoiceAudio],
  );

  const handleCompareVoices = useCallback(async () => {
    const text = voicePreviewText.trim();
    const voices = comparisonVoices.length
      ? comparisonVoices
      : [ttsPreviewVoice || realtimeVoice];
    const uniqueVoices = Array.from(new Set(voices.filter(Boolean)));
    if (!text || uniqueVoices.length === 0) {
      setVoicePreviewError("Escribe una frase y elige al menos una voz.");
      return;
    }
    voiceAbortRef.current?.abort();
    voiceAudioRef.current?.pause();
    if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
    voiceAudioUrlRef.current = null;
    clearVoiceSamples();
    const controller = new AbortController();
    voiceAbortRef.current = controller;
    setVoicePreviewStatus("generating");
    setVoicePreviewError("");
    const generated: Array<{ voice: string; url: string }> = [];
    try {
      for (const voice of uniqueVoices) {
        const blob = await previewAssistantVoice(
          clinicId,
          buildVoicePreviewPayload(voice),
          controller.signal,
        );
        const url = URL.createObjectURL(blob);
        generated.push({ voice, url });
      }
      voiceSampleUrlsRef.current = generated.map((sample) => sample.url);
      setVoiceSamples(generated);
      if (generated[0]) handlePlaySample(generated[0].url);
      else setVoicePreviewStatus("idle");
    } catch (error) {
      for (const sample of generated) URL.revokeObjectURL(sample.url);
      if (error instanceof Error && error.name === "AbortError") return;
      const message =
        error instanceof Error ? error.message : "No se pudo comparar voces.";
      setVoicePreviewError(message);
      setVoicePreviewStatus("idle");
      toast.error(message);
    } finally {
      if (voiceAbortRef.current === controller) voiceAbortRef.current = null;
    }
  }, [
    buildVoicePreviewPayload,
    clearVoiceSamples,
    clinicId,
    comparisonVoices,
    handlePlaySample,
    realtimeVoice,
    ttsPreviewVoice,
    voicePreviewText,
  ]);

  const handleFormSubmit = handleSubmit(async (values) => {
    stopVoicePreview();
    stopRealtimePreview("save");
    await onSubmit(values);
  });

  return (
    <form className="space-y-7" onSubmit={handleFormSubmit}>
      <div className="rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4">
        <Label htmlFor="assistant-template">Plantilla rápida</Label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <Select
            id="assistant-template"
            defaultValue=""
            onChange={(event) => {
              const template = event.target.value as AssistantTemplateName;
              if (template) reset(applyAssistantTemplate(getValues(), template));
              event.target.value = "";
            }}
          >
            <option value="">Seleccionar plantilla…</option>
            {assistantTemplateNames.map((template) => (
              <option key={template} value={template}>
                {template}
              </option>
            ))}
          </Select>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              reset({
                ...getValues(),
                first_message: assistantConfigDefaults.first_message,
                system_prompt: assistantConfigDefaults.system_prompt,
                safety_prompt: assistantConfigDefaults.safety_prompt,
                booking_policy_prompt:
                  assistantConfigDefaults.booking_policy_prompt,
                cancellation_policy_prompt:
                  assistantConfigDefaults.cancellation_policy_prompt,
                transfer_policy_prompt:
                  assistantConfigDefaults.transfer_policy_prompt,
                tone: assistantConfigDefaults.tone,
                response_length: assistantConfigDefaults.response_length,
                ask_patient_name: assistantConfigDefaults.ask_patient_name,
                ask_patient_phone: assistantConfigDefaults.ask_patient_phone,
                ask_general_reason: assistantConfigDefaults.ask_general_reason,
                allow_booking_without_worker:
                  assistantConfigDefaults.allow_booking_without_worker,
                allow_bookings: assistantConfigDefaults.allow_bookings,
                allow_price_answers: assistantConfigDefaults.allow_price_answers,
                ask_service: assistantConfigDefaults.ask_service,
                max_proposed_slots: assistantConfigDefaults.max_proposed_slots,
                max_consecutive_questions:
                  assistantConfigDefaults.max_consecutive_questions,
                conversation_style: assistantConfigDefaults.conversation_style,
                initiative_level: assistantConfigDefaults.initiative_level,
                commercial_call_handling:
                  assistantConfigDefaults.commercial_call_handling,
                allow_cancellations: assistantConfigDefaults.allow_cancellations,
                allow_reschedules: assistantConfigDefaults.allow_reschedules,
                natural_confirmation_required:
                  assistantConfigDefaults.natural_confirmation_required,
                avoid_exact_confirmation_phrases:
                  assistantConfigDefaults.avoid_exact_confirmation_phrases,
                additional_instructions:
                  assistantConfigDefaults.additional_instructions,
                forbidden_phrases: assistantConfigDefaults.forbidden_phrases,
                no_availability_message:
                  assistantConfigDefaults.no_availability_message,
                missing_calendar_message:
                  assistantConfigDefaults.missing_calendar_message,
                emergency_message: assistantConfigDefaults.emergency_message,
                human_transfer_message:
                  assistantConfigDefaults.human_transfer_message,
                human_transfer_rules:
                  assistantConfigDefaults.human_transfer_rules,
                commercial_call_message:
                  assistantConfigDefaults.commercial_call_message,
                conversation_extra_rules:
                  assistantConfigDefaults.conversation_extra_rules,
                closing_message: assistantConfigDefaults.closing_message,
                use_prices: assistantConfigDefaults.use_prices,
                use_knowledge_base: assistantConfigDefaults.use_knowledge_base,
                strict_calendar_mode:
                  assistantConfigDefaults.strict_calendar_mode,
              })
            }
          >
            <RefreshCcw className="size-4" />
            Restaurar prompt recomendado
          </Button>
        </div>
        <p className="mt-2 text-xs text-[#6f7c92]">
          Cambia saludo y prompts. Conserva nombre, modelo, voz, estado,
          privacidad y retención.
        </p>
      </div>
      <div
        role="tablist"
        aria-label="Secciones de configuración del asistente"
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
      >
        {assistantConfigTabs.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-xl border px-3 py-2 text-left transition ${
                selected
                  ? "border-[#315efb] bg-[#eef2ff] text-[#1d3fb7] shadow-sm"
                  : "border-[#dfe4ec] bg-white text-[#526078] hover:bg-[#f7f9fc]"
              }`}
            >
              <span className="block text-sm font-semibold">{tab.label}</span>
              <span className="mt-0.5 block text-xs opacity-75">
                {tab.help}
              </span>
            </button>
          );
        })}
      </div>
      <div className="space-y-7">
        <div className="space-y-7">
          <div className={activeTab === "settings" ? "contents" : "hidden"}>
          <div className="rounded-2xl border border-[#dce4ff] bg-[#f8faff] p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-base font-semibold text-[#27334a]">
                  <Mic2 className="size-5 text-[#315efb]" />
                  Prueba en tiempo real
                </div>
                <p className="mt-1 text-sm leading-6 text-[#6f7c92]">
                  Habla por el micrófono y escucha al bot con el modelo, prompt,
                  voz, reglas y tools actuales, incluso sin guardar.
                </p>
                <p className="mt-1 text-xs text-[#7d8899]">
                  Estado: {realtimeStatus}
                  {realtimeSessionId ? ` · sesión ${realtimeSessionId.slice(0, 8)}` : ""}
                </p>
              </div>
              <Button
                type="button"
                size="lg"
                className="min-h-12"
                onClick={() => void handleToggleRealtimePreview()}
                disabled={isPending}
              >
                <Mic2 className="size-5" />
                {realtimeStatus === "connecting" ||
                realtimeStatus === "listening" ||
                realtimeStatus === "speaking" ||
                realtimeStatus === "interrupted"
                  ? "Detener prueba"
                  : "Probar conversación real"}
              </Button>
            </div>
            <div className="mt-4 grid gap-2 rounded-xl border border-[#dce4ff] bg-white/80 p-3 text-xs text-[#526078] sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <span className="font-semibold text-[#27334a]">Modo</span>
                <p>
                  {usesExternalVoiceProvider || callAudioMode === "vps_media_bridge"
                    ? "VPS Media Bridge"
                    : "OpenAI Hosted SIP"}
                </p>
              </div>
              <div>
                <span className="font-semibold text-[#27334a]">Proveedor</span>
                <p>
                  {selectedVoiceProvider?.display_name ?? voiceProvider}
                  {selectedVoiceProvider?.configured ? " · credenciales OK" : " · falta credencial"}
                </p>
              </div>
              <div>
                <span className="font-semibold text-[#27334a]">Voz / TTS</span>
                <p>
                  {(voiceId || ttsPreviewVoice || realtimeVoice) || "sin voz"} ·{" "}
                  {ttsModel || realtimeModel}
                </p>
              </div>
              <div>
                <span className="font-semibold text-[#27334a]">Locale / codec</span>
                <p>
                  {voiceLocale || "sin locale"} · {telephonyCodec.toUpperCase()}
                </p>
              </div>
              <div className="sm:col-span-2 lg:col-span-4">
                <span className="font-semibold text-[#27334a]">
                  Parámetros numéricos
                </span>
                <p>
                  velocidad {voiceSpeed || "1"} · pitch {voicePitch || "0"} ·
                  estabilidad {voiceStability || "—"} · similitud{" "}
                  {voiceSimilarity || "—"} · temperatura voz{" "}
                  {voiceTemperature || "—"} · idle{" "}
                  {idleTimeoutMs ? `${idleTimeoutMs} ms` : "auto"}
                </p>
              </div>
            </div>
            {realtimeError ? (
              <p className="mt-3 text-sm font-medium text-[#bd3341]">
                {realtimeError}
              </p>
            ) : null}
          </div>

          <FormSection
            title="1. Identidad del asistente"
            description="Nombre interno, idioma, tono y longitud de respuesta."
          >
            <div>
              <Label htmlFor="assistant-name">Nombre de configuración</Label>
              <Input
                id="assistant-name"
                className="mt-1.5"
                {...register("name")}
              />
              <FieldError message={errors.name?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-language">Idioma</Label>
              <Select
                id="assistant-language"
                className="mt-1.5"
                {...register("language")}
              >
                {options.languages.map((language) => (
                  <option key={language.id} value={language.id}>
                    {language.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-tone">Tono</Label>
              <Select id="assistant-tone" className="mt-1.5" {...register("tone")}>
                <option value="profesional">Profesional</option>
                <option value="cercano">Cercano</option>
                <option value="comercial">Comercial</option>
                <option value="breve">Breve</option>
                <option value="formal">Formal</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-response-length">
                Longitud de respuesta
              </Label>
              <Select
                id="assistant-response-length"
                className="mt-1.5"
                {...register("response_length")}
              >
                <option value="corta">Corta</option>
                <option value="normal">Normal</option>
                <option value="detallada">Detallada</option>
              </Select>
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "settings" ? "contents" : "hidden"}>
          <FormSection
            title="2. Voz y llamada"
            description="Modo de llamada, proveedor, modelo, voz, idioma, códec y pruebas."
          >
            <div>
              <Label htmlFor="assistant-model">Modelo Realtime</Label>
              <Select
                id="assistant-model"
                className="mt-1.5"
                {...register("realtime_model")}
              >
                {options.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.realtime_model?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice">Voz</Label>
              <Select
                id="assistant-voice"
                className="mt-1.5"
                {...register("realtime_voice")}
              >
                {options.voices.map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {voice.label}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Para España o galego, controla idioma y acento desde el prompt.
                Marin y Cedar quedan como voces recomendadas.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-call-audio-mode">Modo de llamada</Label>
              <Select
                id="assistant-call-audio-mode"
                className="mt-1.5"
                {...register("call_audio_mode")}
                disabled={usesExternalVoiceProvider}
              >
                <option value="openai_hosted_sip">
                  OpenAI Hosted SIP
                </option>
                <option value="vps_media_bridge">VPS Media Bridge</option>
              </Select>
              <FieldError message={errors.call_audio_mode?.message} />
              <p className="mt-1 text-xs text-[#7d8899]">
                OpenAI Hosted SIP mantiene el flujo actual. VPS Media Bridge
                enruta SIP/RTP por tu VPS.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-voice-provider">Proveedor de voz</Label>
              <Select
                id="assistant-voice-provider"
                className="mt-1.5"
                {...register("voice_provider")}
              >
                {providerOptions.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.display_name}
                    {provider.configured ? "" : " · sin credenciales"}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.voice_provider?.message} />
              <p className="mt-1 text-xs text-[#7d8899]">
                Si no es OpenAI, se usa obligatoriamente VPS Media Bridge.
              </p>
              {selectedVoiceProvider?.notes ? (
                <p className="mt-1 text-xs text-[#7d8899]">
                  {selectedVoiceProvider.notes}
                </p>
              ) : null}
              {selectedVoiceProvider && !selectedVoiceProvider.configured ? (
                <p className="mt-1 text-xs font-medium text-[#9b6a00]">
                  Este proveedor no tiene credenciales configuradas. Puedes
                  guardar ajustes, pero el preview devolverá el nombre de la
                  variable que falta.
                </p>
              ) : null}
              {voiceProvider === "azure" && !selectedVoiceProvider?.configured ? (
                <p className="mt-1 text-xs font-medium text-[#bd3341]">
                  Falta AZURE_SPEECH_KEY o AZURE_SPEECH_REGION en el backend.
                  Si pones región aquí, solo queda obligatoria la key.
                </p>
              ) : null}
              <Button
                type="button"
                variant="outline"
                className="mt-3"
                onClick={applySabelaVoice}
              >
                Usar Sabela galego
              </Button>
              <p className="mt-1 text-xs text-[#7d8899]">
                Aplica Azure, gl-ES-SabelaNeural, gl-ES, PCMA y VPS Media Bridge.
              </p>
            </div>
            <div className="sm:col-span-2 rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4 text-sm leading-6 text-[#526078]">
              {usesExternalVoiceProvider ? (
                <>
                  <strong className="text-[#27334a]">
                    Voz externa seleccionada.
                  </strong>{" "}
                  VoIP Studio debe llamar a tu SIP/RTP en VPS; el VPS conecta
                  con OpenAI Realtime WebSocket, genera TTS externo y devuelve
                  RTP. OpenAI Hosted SIP solo puede usar voces OpenAI.
                  Configura VoIP Studio con sip:bot@sip.autogal.es:6060.
                </>
              ) : (
                <>
                  <strong className="text-[#27334a]">
                    Flujo compatible actual.
                  </strong>{" "}
                  Puedes mantener VoIP Studio → OpenAI SIP → webhook FastAPI,
                  o elegir VPS Media Bridge para probar todo desde tu VPS.
                </>
              )}
            </div>
            <div>
              <Label htmlFor="assistant-temperature">Temperatura opcional</Label>
              <Input
                id="assistant-temperature"
                type="number"
                min="0"
                max="2"
                step="0.1"
                className="mt-1.5"
                {...register("temperature")}
              />
              <FieldError message={errors.temperature?.message} />
            </div>
            <label className="mt-6 flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
              <input
                type="checkbox"
                className="size-4 accent-[#315efb]"
                {...register("is_active")}
              />
              Activar al guardar
            </label>
            <div className="sm:col-span-2 rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#27334a]">
                    <Volume2 className="size-4 text-[#315efb]" />
                    Probar voz
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[#6f7c92]">
                    Genera audio corto con la voz seleccionada. Usa los valores
                    actuales del formulario, aunque todavía no hayas guardado.
                  </p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[#526078]">
                  {realtimeVoice} · {realtimeModel}
                </span>
              </div>
              <div className="mt-3">
                <Label htmlFor="assistant-voice-preview">Frase de prueba</Label>
                <Textarea
                  id="assistant-voice-preview"
                  value={voicePreviewText}
                  onChange={(event) => setVoicePreviewText(event.target.value)}
                  className="mt-1.5 min-h-24"
                  maxLength={500}
                />
                <p className="mt-1 text-xs text-[#7d8899]">
                  {voicePreviewText.length}/500 caracteres. Esta prueba no crea
                  conversación ni se guarda.
                </p>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  onClick={() => void handleListenVoice()}
                  disabled={voicePreviewStatus === "generating"}
                >
                  <Volume2 className="size-4" />
                  {voicePreviewStatus === "generating"
                    ? "Generando..."
                    : "Escuchar"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleToggleVoiceAudio}
                  disabled={
                    voicePreviewStatus === "generating" || !voiceAudioRef.current
                  }
                >
                  {voicePreviewStatus === "playing" ? (
                    <Pause className="size-4" />
                  ) : (
                    <Play className="size-4" />
                  )}
                  {voicePreviewStatus === "playing" ? "Pausar" : "Reproducir"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleRepeatVoiceAudio}
                  disabled={
                    voicePreviewStatus === "generating" || !voiceAudioRef.current
                  }
                >
                  <RefreshCcw className="size-4" />
                  Repetir
                </Button>
                <span className="text-xs font-medium text-[#6f7c92]">
                  {voicePreviewStatus === "generating"
                    ? "generando audio"
                    : voicePreviewStatus === "playing"
                      ? "reproduciendo"
                      : voicePreviewStatus === "paused"
                        ? "pausado"
                        : "listo"}
                </span>
              </div>
              {voicePreviewError ? (
                <p className="mt-2 text-xs font-medium text-[#bd3341]">
                  {voicePreviewError}
                </p>
              ) : null}
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "settings" ? "contents" : "hidden"}>
          <FormSection
            title="Perfil de voz"
            description="Define cómo habla el asistente: ritmo, pausas, lectura de datos y disclosure IA."
          >
            <div>
              <Label htmlFor="assistant-voice-preset">Preset de voz</Label>
              <Select
                id="assistant-voice-preset"
                className="mt-1.5"
                value={voicePreset}
                onChange={(event) => {
                  const preset = event.target.value as VoicePresetName;
                  if (preset) reset(applyVoicePreset(getValues(), preset));
                  else setValue("voice_preset", "");
                }}
              >
                <option value="">Personalizado</option>
                {voicePresetNames.map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Rellena automáticamente tono, pausas y estilos de lectura.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-tts-model">Modelo TTS externo</Label>
              <Input
                id="assistant-tts-model"
                list="assistant-tts-model-options"
                className="mt-1.5"
                placeholder={
                  providerModelChoices.length
                    ? "Elige o escribe un modelo"
                    : "Ej. eleven_multilingual_v2"
                }
                {...register("tts_model")}
              />
              <datalist id="assistant-tts-model-options">
                {providerModelChoices.map((model) => (
                  <option key={model} value={model} />
                ))}
              </datalist>
              <p className="mt-1 text-xs text-[#7d8899]">
                Solo se usa en VPS Media Bridge o integraciones TTS externas.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-voice-id">Voice ID externo</Label>
              {providerVoiceChoices.length > 0 ? (
                <Select
                  id="assistant-voice-id"
                  className="mt-1.5"
                  value={voiceId}
                  onChange={(event) => {
                    const selectedVoiceId = event.target.value;
                    if (
                      voiceProvider === "azure" &&
                      selectedVoiceId === "gl-ES-SabelaNeural"
                    ) {
                      applySabelaVoice();
                      return;
                    }
                    setValue("voice_id", selectedVoiceId, {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                    const selectedVoice = providerVoiceChoices.find(
                      (voice) => voice.id === selectedVoiceId,
                    );
                    if (selectedVoice?.model) {
                      setValue("tts_model", selectedVoice.model, {
                        shouldDirty: true,
                        shouldValidate: true,
                      });
                    }
                    if (selectedVoice?.locale) {
                      setValue("voice_locale", selectedVoice.locale, {
                        shouldDirty: true,
                        shouldValidate: true,
                      });
                    }
                  }}
                >
                  <option value="">Selecciona voz del catálogo</option>
                  {providerVoiceChoices.map((voice) => (
                    <option key={`${voice.model}:${voice.id}`} value={voice.id}>
                      {voice.label}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  id="assistant-voice-id"
                  className="mt-1.5"
                  placeholder="ID de voz del proveedor"
                  {...register("voice_id")}
                />
              )}
              {providerVoicesQuery.isLoading ? (
                <p className="mt-1 text-xs text-[#7d8899]">
                  Cargando catálogo de voces...
                </p>
              ) : null}
              {providerVoicesQuery.isError ? (
                <p className="mt-1 text-xs font-medium text-[#bd3341]">
                  No se pudo cargar el catálogo. Puedes escribir el ID manualmente.
                </p>
              ) : null}
            </div>
            <div>
              <Label htmlFor="assistant-voice-locale">Locale de voz</Label>
              <Input
                id="assistant-voice-locale"
                className="mt-1.5"
                placeholder="es-ES, gl-ES..."
                {...register("voice_locale")}
              />
            </div>
            <div>
              <Label htmlFor="assistant-voice-gender">Género/estilo</Label>
              <Input
                id="assistant-voice-gender"
                className="mt-1.5"
                placeholder="female, male, neutral..."
                {...register("voice_gender")}
              />
            </div>
            {voiceProvider === "azure" ? (
              <>
                <div>
                  <Label htmlFor="assistant-azure-region">
                    Región Azure Speech
                  </Label>
                  <Input
                    id="assistant-azure-region"
                    className="mt-1.5"
                    placeholder="Ej. westeurope"
                    {...register("azure_speech_region")}
                  />
                  <p className="mt-1 text-xs text-[#7d8899]">
                    Si se deja vacío, usa AZURE_SPEECH_REGION del backend.
                  </p>
                </div>
                <div>
                  <Label htmlFor="assistant-voice-style">Estilo Azure</Label>
                  <Input
                    id="assistant-voice-style"
                    className="mt-1.5"
                    placeholder="Opcional. Ej. cheerful, customer-service"
                    {...register("voice_style")}
                  />
                  <p className="mt-1 text-xs text-[#7d8899]">
                    No todas las voces aceptan estilos. Vacío es más seguro.
                  </p>
                </div>
              </>
            ) : null}
            <div>
              <Label htmlFor="assistant-output-audio-format">
                Formato audio salida
              </Label>
              <Select
                id="assistant-output-audio-format"
                className="mt-1.5"
                {...register("output_audio_format")}
              >
                {outputAudioFormats.map((format) => (
                  <option key={format} value={format}>
                    {format.toUpperCase()}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Formato intermedio antes de codificar para telefonía.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-telephony-codec">
                Codec telefonía
              </Label>
              <Select
                id="assistant-telephony-codec"
                className="mt-1.5"
                {...register("telephony_codec")}
              >
                {telephonyCodecs.map((codec) => (
                  <option key={codec} value={codec}>
                    {codec === "pcmu"
                      ? "PCMU / G.711 µ-law"
                      : codec === "pcma"
                        ? "PCMA / G.711 A-law"
                        : codec.toUpperCase()}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-voice-speed">Velocidad voz externa</Label>
              <Input
                id="assistant-voice-speed"
                type="number"
                min="0.25"
                max="4"
                step="0.05"
                className="mt-1.5"
                {...register("voice_speed")}
              />
              <FieldError message={errors.voice_speed?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice-pitch">Pitch</Label>
              <Input
                id="assistant-voice-pitch"
                type="number"
                min="-24"
                max="24"
                step="0.1"
                className="mt-1.5"
                {...register("voice_pitch")}
              />
              <FieldError message={errors.voice_pitch?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice-stability">Estabilidad</Label>
              <Input
                id="assistant-voice-stability"
                type="number"
                min="0"
                max="1"
                step="0.05"
                className="mt-1.5"
                placeholder="Opcional"
                {...register("voice_stability")}
              />
              <FieldError message={errors.voice_stability?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice-similarity">Similitud</Label>
              <Input
                id="assistant-voice-similarity"
                type="number"
                min="0"
                max="1"
                step="0.05"
                className="mt-1.5"
                placeholder="Opcional"
                {...register("voice_similarity")}
              />
              <FieldError message={errors.voice_similarity?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice-temperature">
                Temperatura voz
              </Label>
              <Input
                id="assistant-voice-temperature"
                type="number"
                min="0"
                max="2"
                step="0.05"
                className="mt-1.5"
                placeholder="Opcional"
                {...register("voice_temperature")}
              />
              <FieldError message={errors.voice_temperature?.message} />
            </div>
            <label className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
              <input
                type="checkbox"
                className="size-4 accent-[#315efb]"
                {...register("external_voice_legal_confirmed")}
              />
              Confirmo derechos de uso de voz externa/custom
            </label>
            {requiresLegalConfirmation && !externalVoiceLegalConfirmed ? (
              <div className="sm:col-span-2 rounded-xl border border-[#ffd4d8] bg-[#fff6f7] p-4 text-sm text-[#9b2836]">
                Este proveedor puede usarse con voces clonadas o custom. Debes
                confirmar derechos legales antes de guardar.
              </div>
            ) : null}
            <div>
              <Label htmlFor="assistant-tts-preview-voice">
                Voz para pruebas TTS
              </Label>
              <Select
                id="assistant-tts-preview-voice"
                className="mt-1.5"
                {...register("tts_preview_voice")}
              >
                <option value="">Usar voz Realtime ({realtimeVoice})</option>
                {providerVoiceChoices.map((voice) => (
                  <option key={`${voice.model}:${voice.id}`} value={voice.id}>
                    {voice.label}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Solo afecta a pruebas de audio. Las llamadas usan la voz Realtime.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-fallback-voice">Voz fallback</Label>
              <Select
                id="assistant-fallback-voice"
                className="mt-1.5"
                {...register("fallback_voice")}
              >
                <option value="">Sin fallback</option>
                {providerVoiceChoices.map((voice) => (
                  <option key={`${voice.model}:${voice.id}`} value={voice.id}>
                    {voice.label}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Si el proveedor rechaza la voz principal, se prueba esta.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-preview-format">Formato preview</Label>
              <Select
                id="assistant-preview-format"
                className="mt-1.5"
                {...register("preview_audio_format")}
              >
                <option value="mp3">MP3</option>
                <option value="wav">WAV</option>
                <option value="opus">Opus</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-speech-speed">Velocidad</Label>
              <Input
                id="assistant-speech-speed"
                type="number"
                min="0.8"
                max="1.2"
                step="0.05"
                className="mt-1.5"
                value={speechSpeedToNumber(speechSpeed)}
                onChange={(event) =>
                  setValue(
                    "speech_speed",
                    speechSpeedFromNumber(Number(event.target.value)),
                  )
                }
              />
              <p className="mt-1 text-xs text-[#7d8899]">
                1 es natural; menos habla más despacio, más habla más ágil.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-pause-style">Pausas</Label>
              <Input
                id="assistant-pause-style"
                type="number"
                min="0.6"
                max="1.6"
                step="0.1"
                className="mt-1.5"
                value={pauseStyleToNumber(pauseStyle)}
                onChange={(event) =>
                  setValue(
                    "pause_style",
                    pauseStyleFromNumber(Number(event.target.value)),
                  )
                }
              />
              <p className="mt-1 text-xs text-[#7d8899]">
                1 es natural; menos recorta pausas, más deja respirar.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-phone-reading">Lectura teléfonos</Label>
              <Select
                id="assistant-phone-reading"
                className="mt-1.5"
                {...register("phone_reading_style")}
              >
                <option value="digits">Dígito a dígito</option>
                <option value="groups">En grupos</option>
                <option value="natural">Natural</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-date-reading">Lectura fechas</Label>
              <Select
                id="assistant-date-reading"
                className="mt-1.5"
                {...register("date_reading_style")}
              >
                <option value="natural">Natural</option>
                <option value="numeric">Numérica</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-price-reading">Lectura precios</Label>
              <Select
                id="assistant-price-reading"
                className="mt-1.5"
                {...register("price_reading_style")}
              >
                <option value="brief">Breve</option>
                <option value="clear">Clara</option>
                <option value="detailed">Detallada</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-idle-timeout">
                Timeout inactividad (ms)
              </Label>
              <Input
                id="assistant-idle-timeout"
                type="number"
                min="1000"
                max="60000"
                step="500"
                className="mt-1.5"
                placeholder="Por defecto"
                {...register("idle_timeout_ms")}
              />
              <FieldError message={errors.idle_timeout_ms?.message} />
              <p className="mt-1 text-xs text-[#7d8899]">
                Déjalo vacío para usar el valor por defecto de OpenAI.
              </p>
            </div>
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              <label className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
                <input
                  type="checkbox"
                  className="size-4 accent-[#315efb]"
                  {...register("allow_interruptions")}
                />
                Permitir interrupciones naturales
              </label>
              <label className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
                <input
                  type="checkbox"
                  className="size-4 accent-[#315efb]"
                  {...register("ai_disclosure_enabled")}
                />
                Avisar que es asistente virtual
              </label>
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-ai-disclosure">
                Mensaje disclosure IA
              </Label>
              <Textarea
                id="assistant-ai-disclosure"
                className="mt-1.5 min-h-20"
                {...register("ai_disclosure_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-voice-instructions">
                Instrucciones de voz
              </Label>
              <Textarea
                id="assistant-voice-instructions"
                className="mt-1.5 min-h-36"
                {...register("voice_instructions")}
              />
              <p className="mt-1 text-xs text-[#7d8899]">
                No pongas reglas clínicas aquí. Usa este campo solo para estilo,
                ritmo, acento y lectura de datos.
              </p>
            </div>
            <div className="sm:col-span-2 rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#27334a]">
                    <Volume2 className="size-4 text-[#315efb]" />
                    Comparador de voces
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[#6f7c92]">
                    Marca varias voces y genera muestras con los cambios actuales
                    del formulario, aunque no estén guardados.
                  </p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[#526078]">
                  {(ttsPreviewVoice || realtimeVoice)} · {previewAudioFormat}
                </span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {providerVoiceChoices.map((voice) => (
                  <label
                    key={`${voice.model}:${voice.id}`}
                    className="flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      className="size-4 accent-[#315efb]"
                      value={voice.id}
                      checked={comparisonVoices.includes(voice.id)}
                      onChange={(event) => {
                        const value = event.target.value;
                        setComparisonVoices((current) =>
                          event.target.checked
                            ? Array.from(new Set([...current, value]))
                            : current.filter((item) => item !== value),
                        );
                      }}
                    />
                    {voice.label}
                  </label>
                ))}
              </div>
              {providerVoiceChoices.length === 0 ? (
                <p className="mt-2 text-xs text-[#7d8899]">
                  Este proveedor no expone voces todavía. Configura credenciales
                  y sincroniza catálogo, o escribe un Voice ID manual.
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void handleCompareVoices()}
                  disabled={voicePreviewStatus === "generating"}
                >
                  <Mic2 className="size-4" />
                  Comparar voces
                </Button>
                {voiceSamples.map((sample) => (
                  <Button
                    key={sample.voice}
                    type="button"
                    variant="outline"
                    onClick={() => handlePlaySample(sample.url)}
                  >
                    <Play className="size-4" />
                    {sample.voice}
                  </Button>
                ))}
              </div>
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "settings" ? "contents" : "hidden"}>
          <FormSection
            title="3. Primer mensaje"
            description="Saludo que verá también la consola de prueba."
          >
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-first-message">Primer mensaje</Label>
              <Textarea
                id="assistant-first-message"
                className="mt-1.5 min-h-28"
                {...register("first_message")}
              />
              <FieldError message={errors.first_message?.message} />
            </div>
            <div className="sm:col-span-2 rounded-xl border bg-[#fbfcfe] p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-[#7a8598]">
                <Volume2 className="size-4" />
                Preview del primer mensaje
              </div>
              <p className="mt-2 text-sm leading-6 text-[#47546a]">
                {firstMessage || "El saludo aparecerá aquí."}
              </p>
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "conversation" ? "contents" : "hidden"}>
          <FormSection
            title="Comportamiento conversacional"
            description="Control flexible para sonar natural sin crear un flujo rígido."
          >
            <div>
              <Label htmlFor="assistant-conversation-style">Estilo</Label>
              <Select
                id="assistant-conversation-style"
                className="mt-1.5"
                {...register("conversation_style")}
              >
                <option value="natural">Natural</option>
                <option value="formal">Formal</option>
                <option value="comercial">Comercial</option>
                <option value="breve">Breve</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-initiative">Nivel de iniciativa</Label>
              <Select
                id="assistant-initiative"
                className="mt-1.5"
                {...register("initiative_level")}
              >
                <option value="bajo">Bajo</option>
                <option value="medio">Medio</option>
                <option value="alto">Alto</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-max-questions">
                Máximo de preguntas seguidas
              </Label>
              <Input
                id="assistant-max-questions"
                type="number"
                min="1"
                max="5"
                className="mt-1.5"
                {...register("max_consecutive_questions", {
                  valueAsNumber: true,
                })}
              />
              <FieldError message={errors.max_consecutive_questions?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-commercial-handling">
                Llamadas comerciales
              </Label>
              <Select
                id="assistant-commercial-handling"
                className="mt-1.5"
                {...register("commercial_call_handling")}
              >
                <option value="declinar">Declinar amablemente</option>
                <option value="transferir">Transferir a humano</option>
                <option value="responder_basico">Responder básico</option>
              </Select>
            </div>
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              {([
                { name: "allow_bookings", label: "Permitir reservas" },
                { name: "allow_cancellations", label: "Permitir cancelaciones" },
                { name: "allow_reschedules", label: "Permitir cambios de cita" },
                { name: "allow_price_answers", label: "Responder precios" },
                { name: "ask_patient_name", label: "Pedir nombre" },
                { name: "ask_patient_phone", label: "Pedir teléfono" },
                { name: "ask_general_reason", label: "Pedir motivo general" },
                { name: "ask_service", label: "Pedir servicio" },
              ] as const).map(({ name, label }) => (
                <label
                  key={name}
                  className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[#315efb]"
                    {...register(name)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-human-transfer-rules">
                Cuándo transferir a humano
              </Label>
              <Textarea
                id="assistant-human-transfer-rules"
                className="mt-1.5 min-h-24"
                {...register("human_transfer_rules")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-commercial-message">
                Mensaje para spam/comercial
              </Label>
              <Textarea
                id="assistant-commercial-message"
                className="mt-1.5 min-h-24"
                {...register("commercial_call_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-conversation-extra-rules">
                Reglas adicionales libres por clínica
              </Label>
              <Textarea
                id="assistant-conversation-extra-rules"
                className="mt-1.5 min-h-28"
                {...register("conversation_extra_rules")}
              />
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "prompt" ? "contents" : "hidden"}>
          <FormSection
            title="4. Prompt general editable"
            description="La base de comportamiento del asistente antes de añadir servicios y contexto real."
          >
            <div className="sm:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="assistant-system-prompt">Prompt general</Label>
                <span
                  className={`text-xs ${
                    systemPrompt.length > maxPromptLength ||
                    systemPrompt.trim().length < 40
                      ? "text-[#bd3341]"
                      : "text-[#7d8899]"
                  }`}
                >
                  {systemPrompt.length}/{maxPromptLength} caracteres
                </span>
              </div>
              <Textarea
                id="assistant-system-prompt"
                className="mt-1.5 min-h-64 font-mono text-sm"
                {...register("system_prompt")}
              />
              <FieldError message={errors.system_prompt?.message} />
              {systemPrompt.trim().length < 40 ? (
                <p className="mt-1 text-xs text-[#bd3341]">
                  El prompt parece demasiado corto.
                </p>
              ) : null}
              {systemPrompt.length > maxPromptLength ? (
                <p className="mt-1 text-xs text-[#bd3341]">
                  El prompt es demasiado largo para mantenerlo operativo.
                </p>
              ) : null}
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "booking" ? "contents" : "hidden"}>
          <FormSection
            title="5. Reglas de reservas"
            description="Qué datos pide y cómo usa agenda y herramientas."
          >
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              {([
                { name: "ask_patient_name", label: "Pedir nombre" },
                { name: "ask_patient_phone", label: "Pedir teléfono" },
                { name: "ask_general_reason", label: "Pedir motivo general" },
                {
                  name: "allow_booking_without_worker",
                  label: "Permitir reservar sin trabajador concreto",
                },
                { name: "allow_cancellations", label: "Permitir cancelaciones" },
                { name: "allow_reschedules", label: "Permitir cambios de cita" },
                {
                  name: "natural_confirmation_required",
                  label: "Pedir confirmación natural antes de reservar",
                },
                {
                  name: "avoid_exact_confirmation_phrases",
                  label: "No pedir frases exactas",
                },
              ] as const).map(({ name, label }) => (
                <label
                  key={name}
                  className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[#315efb]"
                    {...register(name)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div>
              <Label htmlFor="assistant-max-slots">
                Número máximo de horarios a proponer
              </Label>
              <Input
                id="assistant-max-slots"
                type="number"
                min="1"
                max="10"
                className="mt-1.5"
                {...register("max_proposed_slots", { valueAsNumber: true })}
              />
              <FieldError message={errors.max_proposed_slots?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-booking-policy">Política de reservas</Label>
              <Textarea
                id="assistant-booking-policy"
                className="mt-1.5 min-h-36"
                {...register("booking_policy_prompt")}
              />
              <FieldError message={errors.booking_policy_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-cancellation-policy">
                Política de cancelación
              </Label>
              <Textarea
                id="assistant-cancellation-policy"
                className="mt-1.5 min-h-32"
                {...register("cancellation_policy_prompt")}
              />
              <FieldError message={errors.cancellation_policy_prompt?.message} />
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "safety" ? "contents" : "hidden"}>
          <FormSection
            title="6. Seguridad médica"
            description="Restricciones que siempre se añaden al prompt final."
          >
            <div className="sm:col-span-2">
              <div className="mb-2 flex items-center gap-2 text-sm text-[#8c4b15]">
                <ShieldAlert className="size-4" />
                No elimines el protocolo de urgencias.
              </div>
              <Textarea
                aria-label="Prompt de seguridad"
                className="min-h-44"
                {...register("safety_prompt")}
              />
              <FieldError message={errors.safety_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-emergency-message">
                Mensaje si hay urgencia médica
              </Label>
              <Textarea
                id="assistant-emergency-message"
                className="mt-1.5 min-h-24"
                {...register("emergency_message")}
              />
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "advanced" ? "contents" : "hidden"}>
          <FormSection
            title="7. Transferencia a humano"
            description="Cuándo debe pedir ayuda humana y qué dice."
          >
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-transfer-policy">
                Política de transferencia
              </Label>
              <Textarea
                id="assistant-transfer-policy"
                className="mt-1.5 min-h-36"
                {...register("transfer_policy_prompt")}
              />
              <FieldError message={errors.transfer_policy_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-human-transfer-message">
                Mensaje de transferencia a humano
              </Label>
              <Textarea
                id="assistant-human-transfer-message"
                className="mt-1.5 min-h-24"
                {...register("human_transfer_message")}
              />
            </div>
          </FormSection>

          <FormSection
            title="8. Configuración avanzada"
            description="Mensajes operativos, privacidad y uso del contexto."
          >
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              {([
                { name: "use_prices", label: "Usar precios en el prompt" },
                { name: "use_knowledge_base", label: "Usar knowledge base" },
                { name: "transcript_enabled", label: "Guardar transcripción" },
                { name: "recording_enabled", label: "Habilitar grabación" },
                {
                  name: "strict_calendar_mode",
                  label: "Modo estricto de calendario",
                },
              ] as const).map(({ name, label }) => (
                <label
                  key={name}
                  className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[#315efb]"
                    {...register(name)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div>
              <Label htmlFor="assistant-retention">Retención (días)</Label>
              <Input
                id="assistant-retention"
                type="number"
                min="1"
                max="3650"
                className="mt-1.5"
                {...register("conversation_retention_days", {
                  valueAsNumber: true,
                })}
              />
              <FieldError message={errors.conversation_retention_days?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-additional-instructions">
                Instrucciones adicionales libres
              </Label>
              <Textarea
                id="assistant-additional-instructions"
                className="mt-1.5 min-h-28"
                {...register("additional_instructions")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-forbidden-phrases">
                Palabras/frases prohibidas
              </Label>
              <Textarea
                id="assistant-forbidden-phrases"
                className="mt-1.5 min-h-24"
                placeholder="Una por línea"
                {...register("forbidden_phrases")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-no-availability">
                Mensaje si no hay disponibilidad
              </Label>
              <Textarea
                id="assistant-no-availability"
                className="mt-1.5 min-h-24"
                {...register("no_availability_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-missing-calendar">
                Mensaje si falta calendario
              </Label>
              <Textarea
                id="assistant-missing-calendar"
                className="mt-1.5 min-h-24"
                {...register("missing_calendar_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-closing-message">
                Mensaje de cierre de llamada/chat
              </Label>
              <Textarea
                id="assistant-closing-message"
                className="mt-1.5 min-h-20"
                {...register("closing_message")}
              />
            </div>
            <div className="sm:col-span-2 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-3 text-xs leading-5 text-[#78591d]">
              La preferencia de grabación se persiste, pero este MVP todavía no
              captura ni almacena audio.
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "preview" ? "contents" : "hidden"}>
          <div className="rounded-xl border bg-[#fbfcfe] p-4">
            <div className="flex items-center gap-2 font-semibold text-[#27334a]">
              <Bot className="size-4 text-[#315efb]" />
              9. Preview final del prompt
            </div>
            <p className="mt-1 text-sm text-[#6f7c92]">
              Guarda la configuración y usa “Previsualizar prompt final” en la
              tarjeta para renderizarlo con servicios, trabajadores y knowledge
              reales de la clínica.
            </p>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border bg-white p-3">
                <p className="text-xs font-semibold uppercase text-[#7a8598]">
                  Primer mensaje
                </p>
                <p className="mt-2 text-sm leading-6 text-[#47546a]">
                  {firstMessage || "El saludo aparecerá aquí."}
                </p>
              </div>
              <div className="rounded-xl border bg-white p-3">
                <p className="text-xs font-semibold uppercase text-[#7a8598]">
                  Prompt general actual
                </p>
                <p className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[#47546a]">
                  {systemPrompt || "El prompt general aparecerá aquí."}
                </p>
              </div>
            </div>
          </div>
          </div>
        </div>

        {false ? <aside className="h-fit rounded-2xl border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 font-semibold text-[#27334a]">
            <CheckCircle2 className="size-4 text-[#315efb]" />
            Estado de configuración
          </div>
          <div className="mt-4 space-y-3">
            {checklist.map((item) => (
              <div key={item.label} className="flex items-start gap-2">
                {item.ok ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#168a53]" />
                ) : (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#c77a10]" />
                )}
                <div>
                  <p className="text-sm font-medium text-[#27334a]">
                    {item.label}
                  </p>
                  {!item.ok ? (
                    <p className="text-xs leading-5 text-[#7a8598]">
                      {item.help}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          {contextWarnings.length ? (
            <div className="mt-4 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-3 text-xs leading-5 text-[#78591d]">
              {contextWarnings.slice(0, 4).map((warning) => (
                <p key={warning}>• {warning}</p>
              ))}
            </div>
          ) : null}
        </aside> : null}
      </div>

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            stopRealtimePreview("cancel");
            stopVoicePreview();
            onCancel();
          }}
        >
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          <Sparkles className="size-4" />
          {isPending ? "Guardando…" : "Guardar configuración"}
        </Button>
      </div>
    </form>
  );
}
