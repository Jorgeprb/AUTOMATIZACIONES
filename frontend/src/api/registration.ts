import { apiRequest } from "@/api/client";
import type { AdminIdentity } from "@/lib/auth";

export interface RegisterPayload {
  name: string; email: string; password: string; repeat_password: string;
  accepted_terms: boolean; accepted_privacy: boolean;
}
export function registerAccount(payload:RegisterPayload):Promise<AdminIdentity>{
  return apiRequest("/auth/register",{method:"POST",body:JSON.stringify(payload)});
}
export function verifyEmail(token:string):Promise<void>{return apiRequest("/auth/verify-email",{method:"POST",body:JSON.stringify({token})});}
export function forgotPassword(email:string):Promise<{message:string}>{return apiRequest("/auth/forgot-password",{method:"POST",body:JSON.stringify({email})});}
export function resetPassword(token:string,password:string,repeatPassword:string):Promise<void>{return apiRequest("/auth/reset-password",{method:"POST",body:JSON.stringify({token,password,repeat_password:repeatPassword})});}
export function createOnboardingClinic(payload:{name:string;timezone:string;main_phone_number:string;email?:string|null;address?:string|null}):Promise<{clinic_id:string;billing_account_id:string}>{return apiRequest("/auth/onboarding/clinic",{method:"POST",body:JSON.stringify(payload)});}

export function createAdditionalClinic(payload:{name:string;timezone:string;main_phone_number:string;email?:string|null;address?:string|null}):Promise<{clinic_id:string;billing_account_id:string}>{return apiRequest("/auth/onboarding/clinics",{method:"POST",body:JSON.stringify(payload)});}
