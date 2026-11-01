/**
 * Utilitas tipe untuk skema hasil generate (openapi.d.ts).
 *
 * Skema backend memakai `extra="allow"`, sehingga openapi-typescript menambahkan
 * `& { [key: string]: unknown }`. Index signature itu membuat `keyof` melebar ke `string`
 * dan menyembunyikan salah ketik nama field; TanpaIndeks membuangnya dan menyisakan field yang dideklarasikan.
 */
export type TanpaIndeks<T> = {
  [K in keyof T as string extends K ? never : number extends K ? never : K]: T[K];
};
