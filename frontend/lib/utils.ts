/**
 * Uygulamanın geliştirme ortamında (local) olup olmadığını kontrol eder.
 * Docker veya Production ortamında false döner.
 */
export const isDev = (): boolean => {
  return process.env.NODE_ENV === "development";
};
