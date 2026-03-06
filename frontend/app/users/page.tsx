"use client";

import { useState, useEffect } from "react";

export default function UsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const companyId = "COMP_EE37F274";

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/users`,
      );
      const data = await response.json();
      if (data.success) {
        setUsers(data.users);
      }
    } catch (error) {
      console.error("Error fetching users:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-slate-900 pb-12" lang="tr">
      <section className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex flex-col gap-2">
          <h2 className="text-3xl font-extrabold tracking-tight">
            Kullanıcı Yönetimi
          </h2>
          <p className="text-slate-500 font-medium">
            Şirket personeli ve yetkilendirmeleri buradan yönetebilirsiniz.
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-xl bg-brand-teal px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 cursor-pointer">
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
            />
          </svg>
          YENİ KULLANICI EKLE
        </button>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm min-h-[500px] flex flex-col">
        <div className="bg-brand-teal p-4 flex items-center justify-between text-white">
          <div className="flex items-center gap-2">
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13.732 11c.996.608 2.268.608 3.268 0"
              />
            </svg>
            <h4 className="text-sm font-bold tracking-widest uppercase">
              PERSONEL LİSTESİ
            </h4>
          </div>
        </div>

        <div className="flex-1 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 text-[10px] font-black text-slate-500 uppercase tracking-widest border-b border-slate-100">
                <th className="px-8 py-5">KULLANICI BİLGİSİ</th>
                <th className="px-8 py-5">E-POSTA</th>
                <th className="px-8 py-5">ROL</th>
                <th className="px-8 py-5">DURUM</th>
                <th className="px-8 py-5 text-right">İŞLEMLER</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-8 py-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <div className="h-8 w-8 border-4 border-slate-200 border-t-brand-teal rounded-full animate-spin"></div>
                      <p className="text-xs font-black text-slate-400 uppercase tracking-widest">
                        Yükleniyor...
                      </p>
                    </div>
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-8 py-20 text-center">
                    <p className="text-sm font-bold text-slate-400 italic">
                      Henüz kullanıcı tanımlanmamış.
                    </p>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr
                    key={user.user_id}
                    className="group hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-8 py-6 font-black text-slate-900 italic uppercase">
                      {user.username}
                    </td>
                    <td className="px-8 py-6 text-xs font-bold text-slate-500">
                      {user.email}
                    </td>
                    <td className="px-8 py-6">
                      <span
                        className={`text-[10px] font-black px-3 py-1.5 rounded-lg uppercase tracking-widest ${user.role === "admin" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}
                      >
                        {user.role}
                      </span>
                    </td>
                    <td className="px-8 py-6">
                      <span className="flex items-center gap-2 text-[10px] font-black text-emerald-600 uppercase tracking-widest">
                        <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]"></span>
                        AKTİF
                      </span>
                    </td>
                    <td className="px-8 py-6 text-right">
                      <button className="p-2.5 rounded-xl border border-slate-100 bg-white text-slate-400 hover:text-red-500 transition-all cursor-pointer">
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2.5}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
