export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  environment: string;
}

export interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}
