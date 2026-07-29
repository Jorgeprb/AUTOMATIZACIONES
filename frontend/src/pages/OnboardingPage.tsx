import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { createOnboardingClinic } from "@/api/registration";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
export function OnboardingPage(){const navigate=useNavigate();const [form,setForm]=useState({name:"",timezone:"Europe/Madrid",main_phone_number:"pending",email:"",address:""});const mutation=useMutation({mutationFn:()=>createOnboardingClinic({...form,email:form.email||null,address:form.address||null}),onSuccess:r=>{toast.success("Clínica creada");window.location.assign(`/clinics/${r.clinic_id}`)},onError:(e:Error)=>toast.error(e.message)});return <div className="mx-auto max-w-2xl space-y-6"><PageHeader title="Configura tu primera clínica" description="Podrás añadir más clínicas desde el mismo BillingAccount."/><Card><CardContent className="space-y-4 p-6"><div><Label>Nombre del negocio</Label><Input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div><div><Label>Zona horaria</Label><Input value={form.timezone} onChange={e=>setForm({...form,timezone:e.target.value})}/></div><div><Label>Email público</Label><Input value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></div><div><Label>Dirección</Label><Input value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></div><Button className="w-full" onClick={()=>mutation.mutate()} disabled={!form.name||mutation.isPending}>Crear clínica</Button><Button variant="ghost" className="w-full" onClick={()=>navigate('/')}>Completar después</Button></CardContent></Card></div>}
