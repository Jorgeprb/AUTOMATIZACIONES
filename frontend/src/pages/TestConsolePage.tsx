import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CalendarCheck,
  Download,
  Pause,
  Play,
  RotateCcw,
  Send,
  Square,
  TerminalSquare,
  UserRound,
  Volume2,
  Wrench,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { listAssistantConfigs, previewPrompt } from "@/api/assistants";
import { listClinics } from "@/api/clinics";
import {
  closeTestSession,
  deleteTestSession,
  sendTestMessage,
  startTestSession,
  synthesizeTestSessionAudio,
} from "@/api/testConsole";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import type { TestSession } from "@/schemas/domain";

const scenarios = [
  "Quiero una cita mañana por la mañana",
  "Cuánto cuesta una limpieza",
  "Quiero cancelar mi cita",
  "Tengo una urgencia médica",
  "Quiero cita con Ana",
  "Me da igual con quién",
];

function StateValue({
  label,
  value,
}: {
  label: string;
  value: string | boolean | null;
}) {
  const rendered =
    typeof value === "boolean" ? (value ? "Sí" : "No") : value || "—";
  return (
    <div className="rounded-xl border border-[#e7eaf0] bg-[#fafbfc] p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8490a2]">
        {label}
      </p>
      <p className="mt-1 truncate text-sm font-medium text-[#344158]">
        {rendered}
      </p>
    </div>
  );
}

export function TestConsolePage() {
  const clinicId = useClinicRoute();
  const navigate = useNavigate();
  const chatEndRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const ttsAbortRef = useRef<AbortController | null>(null);
  const [configId, setConfigId] = useState("");
  const [engine, setEngine] = useState<"simulator" | "openai">("simulator");
  const [useRealCalendar, setUseRealCalendar] = useState(false);
  const [listenVoice, setListenVoice] = useState(false);
  const [audioStatus, setAudioStatus] = useState<
    "idle" | "generating" | "playing" | "paused" | "error"
  >("idle");
  const [audioError, setAudioError] = useState("");
  const [lastAudioText, setLastAudioText] = useState("");
  const [lastSpokenKey, setLastSpokenKey] = useState("");
  const [message, setMessage] = useState("");
  const [testSession, setTestSession] = useState<TestSession | null>(null);
  const chatClosed = Boolean(testSession?.is_closed);

  const stopAudio = useCallback(() => {
    ttsAbortRef.current?.abort();
    ttsAbortRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
    setAudioStatus("idle");
  }, []);

  const lastAssistantMessage = useCallback((session: TestSession | null) => {
    return [...(session?.messages ?? [])]
      .reverse()
      .find((item) => item.role === "assistant");
  }, []);

  const playAudioElement = useCallback(async (audio: HTMLAudioElement) => {
    try {
      await audio.play();
      setAudioStatus("playing");
      setAudioError("");
    } catch {
      setAudioStatus("paused");
      setAudioError("El navegador bloqueó la reproducción automática.");
    }
  }, []);

  const generateAndPlayAudio = useCallback(
    async (session: TestSession, text: string, key: string) => {
      ttsAbortRef.current?.abort();
      audioRef.current?.pause();
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioRef.current = null;
      audioUrlRef.current = null;
      const controller = new AbortController();
      ttsAbortRef.current = controller;
      setAudioStatus("generating");
      setAudioError("");
      setLastSpokenKey(key);
      try {
        const blob = await synthesizeTestSessionAudio(
          session.id,
          text,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => setAudioStatus("idle");
        audio.onpause = () => {
          if (!audio.ended) setAudioStatus("paused");
        };
        audioUrlRef.current = url;
        audioRef.current = audio;
        setLastAudioText(text);
        await playAudioElement(audio);
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "No se pudo generar audio.";
        setAudioStatus("error");
        setAudioError(message);
        toast.error(message);
      } finally {
        if (ttsAbortRef.current === controller) ttsAbortRef.current = null;
      }
    },
    [playAudioElement],
  );

  const clinicsQuery = useQuery({
    queryKey: ["clinics", "test-console"],
    queryFn: () => listClinics({ pageSize: 100 }),
  });
  const configsQuery = useQuery({
    queryKey: ["assistants", clinicId, "test-console"],
    queryFn: () => listAssistantConfigs(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const selectedConfig = configsQuery.data?.items.find(
    (config) => config.id === configId,
  );
  const selectedFlowLabel =
    selectedConfig?.call_audio_mode === "vps_media_bridge" ||
    selectedConfig?.voice_provider !== "openai"
      ? "VPS Media Bridge"
      : "OpenAI Hosted SIP";

  useEffect(() => {
    const active =
      configsQuery.data?.items.find((config) => config.is_active) ??
      configsQuery.data?.items[0];
    if (active && !configsQuery.data?.items.some((item) => item.id === configId)) {
      setConfigId(active.id);
    }
  }, [configId, configsQuery.data]);

  useEffect(() => {
    setTestSession(null);
    stopAudio();
    setLastSpokenKey("");
  }, [clinicId, configId, engine, stopAudio, useRealCalendar]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [testSession?.messages.length]);

  useEffect(() => {
    return () => stopAudio();
  }, [stopAudio]);

  useEffect(() => {
    if (chatClosed) stopAudio();
  }, [chatClosed, stopAudio]);

  useEffect(() => {
    if (!listenVoice || !testSession || chatClosed) return;
    const assistantMessage = lastAssistantMessage(testSession);
    if (!assistantMessage) return;
    const key = `${assistantMessage.created_at}:${assistantMessage.content}`;
    if (key === lastSpokenKey) return;
    void generateAndPlayAudio(testSession, assistantMessage.content, key);
  }, [
    chatClosed,
    generateAndPlayAudio,
    lastAssistantMessage,
    lastSpokenKey,
    listenVoice,
    testSession,
  ]);

  const previewQuery = useQuery({
    queryKey: ["prompt-preview", clinicId, configId, "test-console"],
    queryFn: () => previewPrompt(clinicId as string, configId),
    enabled: Boolean(clinicId && configId),
  });
  const startMutation = useMutation({
    mutationFn: () =>
      startTestSession(clinicId as string, {
        assistant_config_id: configId,
        use_real_calendar: useRealCalendar,
        engine,
      }),
    onSuccess: (data) => {
      setTestSession(data);
      toast.success("Conversación de prueba iniciada");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      sendTestMessage(testSession?.id as string, content),
    onSuccess: (data) => {
      setTestSession(data);
      setMessage("");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const resetMutation = useMutation({
    mutationFn: async () => {
      stopAudio();
      if (testSession) await deleteTestSession(testSession.id);
      return startTestSession(clinicId as string, {
        assistant_config_id: configId,
        use_real_calendar: useRealCalendar,
        engine,
      });
    },
    onSuccess: (data) => {
      setTestSession(data);
      setMessage("");
      setLastSpokenKey("");
      toast.success("Conversación reiniciada");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const closeMutation = useMutation({
    mutationFn: () => closeTestSession(testSession?.id as string),
    onSuccess: (data) => {
      stopAudio();
      setTestSession(data);
      setMessage("");
      toast.success("Chat finalizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const submitMessage = () => {
    const content = message.trim();
    if (!content || sendMutation.isPending || chatClosed) return;
    if (!testSession) {
      toast.error("Inicia primero la conversación");
      return;
    }
    sendMutation.mutate(content);
  };

  const exportConversation = () => {
    if (!testSession) return;
    const blob = new Blob([JSON.stringify(testSession, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `test-session-${testSession.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const replayLastAudio = () => {
    const current = audioRef.current;
    if (current) {
      current.currentTime = 0;
      void playAudioElement(current);
      return;
    }
    const assistantMessage = lastAssistantMessage(testSession);
    if (!testSession || !assistantMessage || chatClosed) return;
    const key = `${assistantMessage.created_at}:${assistantMessage.content}:replay`;
    void generateAndPlayAudio(testSession, assistantMessage.content, key);
  };

  const togglePlayPause = () => {
    const current = audioRef.current;
    if (!current) {
      replayLastAudio();
      return;
    }
    if (audioStatus === "playing") {
      current.pause();
      setAudioStatus("paused");
    } else {
      void playAudioElement(current);
    }
  };

  if (configsQuery.isLoading) return <LoadingState rows={6} />;
  if (configsQuery.error) return <ErrorState error={configsQuery.error} />;

  return (
    <div className="space-y-7">
      <PageHeader
        title="Consola de prueba"
        description="Prueba el prompt y las mismas herramientas del asistente sin teléfono ni SIP."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={!testSession || resetMutation.isPending}
              onClick={() => resetMutation.mutate()}
            >
              <RotateCcw className="size-4" />
              Reset
            </Button>
            <Button
              variant="outline"
              disabled={!testSession || chatClosed || closeMutation.isPending}
              onClick={() => {
                stopAudio();
                closeMutation.mutate();
              }}
            >
              <Square className="size-4" />
              Finalizar chat
            </Button>
            <Button
              variant="outline"
              disabled={!testSession}
              onClick={exportConversation}
            >
              <Download className="size-4" />
              Exportar
            </Button>
          </div>
        }
      />

      <Card>
        <CardContent className="grid gap-4 pt-5 md:grid-cols-2 xl:grid-cols-5">
          <div>
            <Label htmlFor="test-clinic">Clínica</Label>
            <Select
              id="test-clinic"
              className="mt-1.5"
              value={clinicId ?? ""}
              onChange={(event) =>
                navigate(`/clinics/${event.target.value}/test`)
              }
            >
              {clinicsQuery.data?.items.map((clinic) => (
                <option key={clinic.id} value={clinic.id}>
                  {clinic.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="test-config">AssistantConfig</Label>
            <Select
              id="test-config"
              className="mt-1.5"
              value={configId}
              onChange={(event) => setConfigId(event.target.value)}
            >
              {configsQuery.data?.items.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name}
                  {config.is_active ? " · activa" : ""}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="test-engine">Motor textual</Label>
            <Select
              id="test-engine"
              className="mt-1.5"
              value={engine}
              onChange={(event) =>
                setEngine(event.target.value as "simulator" | "openai")
              }
            >
              <option value="simulator">Simulador local seguro</option>
              <option value="openai">Modelo OpenAI</option>
            </Select>
          </div>
          <div className="flex flex-col justify-end gap-3">
            <label className="flex items-center gap-2 text-sm font-medium text-[#37445b]">
              <input
                type="checkbox"
                checked={useRealCalendar}
                onChange={(event) => setUseRealCalendar(event.target.checked)}
                className="size-4 rounded border-[#cfd6e2]"
              />
              Usar Google Calendar real
            </label>
            <Button
              disabled={!configId || startMutation.isPending}
              onClick={() => startMutation.mutate()}
            >
              <Play className="size-4" />
              {testSession ? "Nueva conversación" : "Iniciar conversación"}
            </Button>
          </div>
          <div className="rounded-xl border border-[#e4e8ef] bg-[#fbfcfe] p-3">
            <div className="mb-3 rounded-lg bg-white px-3 py-2 text-xs text-[#526078]">
              <p className="font-semibold text-[#27334a]">{selectedFlowLabel}</p>
              <p>
                {selectedConfig?.voice_provider ?? "openai"} ·{" "}
                {selectedConfig?.voice_id ||
                  selectedConfig?.tts_preview_voice ||
                  selectedConfig?.realtime_voice ||
                  "voz no configurada"}
              </p>
              <p>
                {selectedConfig?.telephony_codec?.toUpperCase() ?? "PCMU"} ·{" "}
                {selectedConfig?.voice_locale ?? "es-ES"}
              </p>
            </div>
            <label className="flex items-center gap-2 text-sm font-medium text-[#37445b]">
              <input
                type="checkbox"
                checked={listenVoice}
                disabled={chatClosed}
                onChange={(event) => {
                  setListenVoice(event.target.checked);
                  if (!event.target.checked) stopAudio();
                }}
                className="size-4 rounded border-[#cfd6e2]"
              />
              Escuchar voz del bot
            </label>
            <p className="mt-1 text-xs text-[#7a8699]">
              {selectedFlowLabel === "VPS Media Bridge"
                ? "Simula modelo texto → TTS provider → audio, sin llamada telefónica."
                : "Reproduce la voz OpenAI configurada para el flujo Hosted SIP."}
            </p>
            <div className="mt-3 flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={!testSession || chatClosed || audioStatus === "generating"}
                onClick={togglePlayPause}
                aria-label={audioStatus === "playing" ? "Pausar audio" : "Reproducir audio"}
              >
                {audioStatus === "playing" ? (
                  <Pause className="size-4" />
                ) : (
                  <Play className="size-4" />
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={
                  !testSession ||
                  chatClosed ||
                  audioStatus === "generating" ||
                  (!lastAudioText && !lastAssistantMessage(testSession))
                }
                onClick={replayLastAudio}
                aria-label="Repetir último audio"
              >
                <RotateCcw className="size-4" />
              </Button>
              <div className="flex items-center gap-1 text-xs text-[#6f7c92]">
                <Volume2 className="size-3.5" />
                {audioStatus === "generating"
                  ? "generando audio"
                  : audioStatus === "playing"
                    ? "reproduciendo"
                    : audioStatus === "paused"
                      ? "pausado"
                      : "listo"}
              </div>
            </div>
            {audioError ? (
              <p className="mt-2 text-xs leading-5 text-[#bd3341]">
                {audioError}
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {useRealCalendar ? (
        <div className="flex gap-3 rounded-xl border border-[#f2d4a3] bg-[#fff8e9] p-4 text-sm text-[#8a5b12]">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          Las confirmaciones crearán o cancelarán eventos reales en Google
          Calendar. El bot aceptará confirmaciones naturales del paciente.
        </div>
      ) : (
        <div className="flex gap-3 rounded-xl border border-[#cfe7d8] bg-[#f1faf4] p-4 text-sm text-[#2f6e49]">
          <CalendarCheck className="mt-0.5 size-5 shrink-0" />
          Modo seguro: calendario fake en memoria. Google Calendar no recibe
          cambios.
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-5 text-[#315efb]" />
                Conversación
                {chatClosed ? (
                  <StatusBadge status="success">Chat finalizado</StatusBadge>
                ) : null}
              </CardTitle>
              <CardDescription>
                Escribe como paciente. La sesión conserva contexto entre turnos.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[500px] space-y-4 overflow-y-auto rounded-xl bg-[#f7f8fa] p-4">
                {testSession?.messages.map((item, index) => (
                  <div
                    key={`${item.created_at}-${index}`}
                    className={`flex gap-3 ${
                      item.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {item.role === "assistant" ? (
                      <div className="grid size-8 shrink-0 place-items-center rounded-full bg-[#e9efff] text-[#315efb]">
                        <Bot className="size-4" />
                      </div>
                    ) : null}
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                        item.role === "user"
                          ? "bg-[#315efb] text-white"
                          : "border border-[#e2e6ed] bg-white text-[#344158]"
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{item.content}</p>
                      {item.tool_calls.length ? (
                        <p className="mt-2 text-xs opacity-70">
                          {item.tool_calls.length} tool(s) ejecutada(s)
                        </p>
                      ) : null}
                    </div>
                    {item.role === "user" ? (
                      <div className="grid size-8 shrink-0 place-items-center rounded-full bg-[#dfe5ef] text-[#536078]">
                        <UserRound className="size-4" />
                      </div>
                    ) : null}
                  </div>
                ))}
                {!testSession ? (
                  <div className="grid h-full place-items-center text-center">
                    <div>
                      <TerminalSquare className="mx-auto size-9 text-[#9aa4b5]" />
                      <p className="mt-3 font-semibold text-[#39465d]">
                        Inicia una conversación
                      </p>
                      <p className="mt-1 text-sm text-[#7a8699]">
                        El modo seguro no toca Google.
                      </p>
                    </div>
                  </div>
                ) : null}
                <div ref={chatEndRef} />
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {scenarios.map((scenario) => (
                  <button
                    key={scenario}
                    type="button"
                    className="rounded-full border border-[#dfe4ec] bg-white px-3 py-1.5 text-xs font-medium text-[#536078] hover:bg-[#f4f6f9]"
                    disabled={chatClosed}
                    onClick={() => setMessage(scenario)}
                  >
                    {scenario}
                  </button>
                ))}
              </div>

              <div className="mt-4 flex gap-3">
                <Textarea
                  value={message}
                  disabled={!testSession || sendMutation.isPending || chatClosed}
                  placeholder={
                    chatClosed
                      ? "Chat finalizado. Pulsa Reset para crear uno nuevo."
                      : "Escribe como si fueras el paciente…"
                  }
                  className="min-h-20"
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submitMessage();
                    }
                  }}
                />
                <Button
                  size="icon"
                  className="mt-auto shrink-0"
                  disabled={
                    !testSession ||
                    !message.trim() ||
                    sendMutation.isPending ||
                    chatClosed
                  }
                  onClick={submitMessage}
                  aria-label="Enviar mensaje"
                >
                  <Send className="size-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <details>
              <summary className="cursor-pointer list-none p-5 font-semibold text-[#27334a]">
                Ver prompt final
              </summary>
              <div className="border-t border-[#e6eaf0] p-5">
                {previewQuery.error ? (
                  <ErrorState error={previewQuery.error} />
                ) : (
                  <Textarea
                    readOnly
                    value={testSession?.prompt ?? previewQuery.data?.prompt ?? ""}
                    className="min-h-[520px] bg-[#111827] font-mono text-xs leading-6 text-[#e5e7eb]"
                  />
                )}
              </div>
            </details>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Estado extraído</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <StateValue
                label="Nombre"
                value={testSession?.state.patient_name ?? null}
              />
              <StateValue
                label="Teléfono"
                value={testSession?.state.patient_phone ?? null}
              />
              <StateValue
                label="Servicio"
                value={testSession?.state.service_name ?? null}
              />
              <StateValue
                label="Trabajador"
                value={testSession?.state.worker_name ?? null}
              />
              <StateValue
                label="Día"
                value={testSession?.state.preferred_date ?? null}
              />
              <StateValue
                label="Franja"
                value={testSession?.state.preferred_time_window ?? null}
              />
              <StateValue
                label="Fase"
                value={testSession?.state.phase ?? null}
              />
              <StateValue
                label="Cita confirmada"
                value={testSession?.state.appointment_confirmed ?? false}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Wrench className="size-4 text-[#315efb]" />
                  Tools
                </CardTitle>
                <CardDescription>Argumentos y resultados reales.</CardDescription>
              </div>
              <StatusBadge status="info">
                {String(testSession?.tool_calls.length ?? 0)}
              </StatusBadge>
            </CardHeader>
            <CardContent>
              <div className="max-h-[520px] space-y-3 overflow-y-auto">
                {testSession?.tool_calls.map((tool, index) => (
                  <details
                    key={`${tool.name}-${index}`}
                    className="rounded-xl border border-[#e4e8ef]"
                  >
                    <summary className="cursor-pointer p-3 font-mono text-xs font-semibold text-[#30405d]">
                      {tool.name}
                    </summary>
                    <div className="border-t border-[#e8ebf0] p-3">
                      <p className="text-xs font-semibold uppercase text-[#7d899b]">
                        Argumentos
                      </p>
                      <pre className="mt-2 overflow-auto rounded-lg bg-[#111827] p-3 text-[11px] text-[#dbe4f3]">
                        {JSON.stringify(tool.arguments, null, 2)}
                      </pre>
                      <p className="mt-3 text-xs font-semibold uppercase text-[#7d899b]">
                        Resultado
                      </p>
                      <pre className="mt-2 overflow-auto rounded-lg bg-[#111827] p-3 text-[11px] text-[#dbe4f3]">
                        {JSON.stringify(tool.result, null, 2)}
                      </pre>
                    </div>
                  </details>
                ))}
                {!testSession?.tool_calls.length ? (
                  <p className="text-sm text-[#7a8699]">
                    Las tools aparecerán cuando el asistente consulte información
                    o calendario.
                  </p>
                ) : null}
              </div>
            </CardContent>
          </Card>

          {testSession?.warnings.length ? (
            <Card className="border-[#f1c7cb]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-[#a6323e]">
                  <AlertTriangle className="size-4" />
                  Advertencias
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {testSession.warnings.map((warning) => (
                  <p key={warning} className="text-sm text-[#8f3841]">
                    {warning}
                  </p>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
