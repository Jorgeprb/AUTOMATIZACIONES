import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("frontend_render_error", { error, componentStack: info.componentStack });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="grid min-h-screen place-items-center bg-muted/30 p-6">
        <Card className="w-full max-w-xl">
          <CardHeader>
            <CardTitle>No se pudo mostrar esta pantalla</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              La sesión sigue protegida. Recarga la aplicación; si el problema persiste,
              facilita el identificador de la petición mostrado por la API.
            </p>
            <Button onClick={() => window.location.reload()}>Recargar</Button>
          </CardContent>
        </Card>
      </main>
    );
  }
}
