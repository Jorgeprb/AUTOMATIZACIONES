import { ArrowLeft } from "lucide-react";

const pages: Record<string, { title: string; sections: Array<[string, string]> }> = {
  "/aviso-legal": {
    title: "Aviso legal",
    sections: [
      ["Titularidad", "Este sitio web pertenece a Autogal. Antes de publicar, completa aquí la razón social, NIF, domicilio y datos registrales de la empresa titular."],
      ["Contacto", "Para consultas relacionadas con el sitio o el servicio, utiliza los canales de contacto publicados por Autogal."],
      ["Uso del sitio", "La información del sitio tiene carácter informativo. No está permitido utilizarlo con fines ilícitos, interferir con su funcionamiento ni intentar acceder a sistemas o datos sin autorización."],
    ],
  },
  "/privacidad": {
    title: "Política de privacidad",
    sections: [
      ["Responsable", "Autogal trata los datos necesarios para gestionar solicitudes, cuentas de cliente y prestación del servicio. Antes de publicar, completa la identidad y los datos de contacto del responsable."],
      ["Datos y finalidad", "Podemos tratar datos identificativos, de contacto, acceso y uso para autenticar cuentas, prestar soporte, administrar clínicas y proteger la plataforma."],
      ["Inicio de sesión con Google", "Cuando accedes con Google recibimos el identificador, email verificado, nombre y, si está disponible, la imagen de perfil. No recibimos tu contraseña de Google."],
      ["Conservación y derechos", "Los datos se conservan durante el tiempo necesario para prestar el servicio y cumplir obligaciones aplicables. Puedes solicitar acceso, rectificación, supresión, oposición o limitación mediante los canales de contacto publicados."],
    ],
  },
  "/cookies": {
    title: "Política de cookies",
    sections: [
      ["Cookies necesarias", "La plataforma utiliza cookies técnicas de sesión y seguridad necesarias para iniciar sesión, proteger formularios y mantener el acceso al panel."],
      ["Servicios externos", "El acceso con Google puede redirigirte a dominios de Google, que aplican sus propias políticas. Autogal no instala cookies publicitarias desde esta web pública en la configuración entregada."],
      ["Configuración", "Puedes borrar o bloquear cookies desde tu navegador, aunque las cookies técnicas son necesarias para utilizar el panel autenticado."],
    ],
  },
};

export function LegalPage({ path }: { path: string }) {
  const page = pages[path] ?? pages["/aviso-legal"];
  return (
    <main className="min-h-screen bg-[#f7f8fa] px-5 py-12 text-[#1f2c44]">
      <article className="mx-auto max-w-3xl rounded-3xl border border-[#e4e8ef] bg-white p-7 shadow-sm sm:p-12">
        <a href="/" className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-[#315efb] hover:underline">
          <ArrowLeft className="size-4" /> Volver a Autogal
        </a>
        <h1 className="text-4xl font-bold tracking-tight">{page.title}</h1>
        <p className="mt-3 text-sm text-[#758096]">Última actualización: 27 de julio de 2026</p>
        <div className="mt-10 space-y-8">
          {page.sections.map(([title, content]) => (
            <section key={title}>
              <h2 className="text-xl font-semibold">{title}</h2>
              <p className="mt-3 leading-7 text-[#55637a]">{content}</p>
            </section>
          ))}
        </div>
      </article>
    </main>
  );
}
