import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  phoneNumberDefaults,
  phoneNumberFormSchema,
  type PhoneNumberFormValues,
} from "@/schemas/phoneNumber";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

export function PhoneNumberForm({
  defaultValues = phoneNumberDefaults,
  onSubmit,
  onCancel,
  isPending,
}: {
  defaultValues?: PhoneNumberFormValues;
  onSubmit: (values: PhoneNumberFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PhoneNumberFormValues>({
    resolver: zodResolver(phoneNumberFormSchema),
    defaultValues,
  });

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  return (
    <form className="space-y-4" onSubmit={handleSubmit(onSubmit)}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="phone-provider">Proveedor</Label>
          <Select
            id="phone-provider"
            className="mt-1.5"
            {...register("provider")}
          >
            <option value="voipstudio">VoIP Studio</option>
            <option value="twilio">Twilio</option>
            <option value="other">Otro</option>
          </Select>
        </div>
        <div>
          <Label htmlFor="phone-label">Etiqueta</Label>
          <Input id="phone-label" className="mt-1.5" {...register("label")} />
          <FieldError message={errors.label?.message} />
        </div>
        <div>
          <Label htmlFor="phone-number">Número</Label>
          <Input
            id="phone-number"
            className="mt-1.5"
            placeholder="+34881170837"
            {...register("phone_number")}
          />
          <FieldError message={errors.phone_number?.message} />
        </div>
        <div>
          <Label htmlFor="phone-webhook">Webhook URL</Label>
          <Input
            id="phone-webhook"
            className="mt-1.5"
            placeholder="https://..."
            {...register("webhook_url")}
          />
          <FieldError message={errors.webhook_url?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="phone-sip">SIP target</Label>
          <Input
            id="phone-sip"
            className="mt-1.5"
            placeholder="sip:PROJECT_ID@sip.api.openai.com;transport=tls"
            {...register("sip_target")}
          />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="phone-notes">Notas</Label>
          <Textarea id="phone-notes" className="mt-1.5" {...register("notes")} />
        </div>
      </div>
      <label className="flex h-10 items-center gap-3 rounded-lg border border-[#dfe4ec] px-3 text-sm font-medium text-[#37445b]">
        <input
          type="checkbox"
          className="size-4 accent-[#315efb]"
          {...register("is_active")}
        />
        Número activo
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Guardando…" : "Guardar número"}
        </Button>
      </div>
    </form>
  );
}
