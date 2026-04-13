"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";

interface Schedule {
  id: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_enabled: boolean;
}

interface ScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  camera: any;
  companyId: string;
}

const DAYS = [
  { value: 7, label: "Her Gün" },
  { value: 1, label: "Pazartesi" },
  { value: 2, label: "Salı" },
  { value: 3, label: "Çarşamba" },
  { value: 4, label: "Perşembe" },
  { value: 5, label: "Cuma" },
  { value: 6, label: "Cumartesi" },
  { value: 0, label: "Pazar" },
];

export default function ScheduleModal({ isOpen, onClose, camera, companyId }: ScheduleModalProps) {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  const [newEntry, setNewEntry] = useState({
    day_of_week: 7,
    start_time: "08:00",
    end_time: "18:00",
  });

  useEffect(() => {
    if (isOpen && camera) {
      fetchSchedules();
    }
  }, [isOpen, camera]);

  const fetchSchedules = async () => {
    setIsLoading(true);
    try {
      const response = await api.camera.listSchedules(companyId, camera.camera_id);
      if (response.success) {
        setSchedules(response.schedules || []);
      }
    } catch (error) {
      console.error("Error fetching schedules:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!camera) return;
    setIsSaving(true);
    try {
      const response = await api.camera.saveSchedule(companyId, camera.camera_id, {
        ...newEntry,
        camera_type: camera.camera_type || "ip_camera",
        is_enabled: true
      });
      if (response.success) {
        fetchSchedules();
      }
    } catch (error) {
      console.error("Error saving schedule:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!camera) return;
    try {
      const response = await api.camera.deleteSchedule(companyId, camera.camera_id, id);
      if (response.success) {
        setSchedules(prev => prev.filter(s => s.id !== id));
      }
    } catch (error) {
      console.error("Error deleting schedule:", error);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-6 sm:p-12 overflow-hidden bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="absolute inset-0" onClick={onClose}></div>
      
      <div className="relative w-full max-w-2xl bg-white rounded-[2.5rem] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.2)] animate-scale-in flex flex-col max-h-full overflow-hidden border border-white/20">
        {/* Modern Header */}
        <div className="bg-brand-teal p-8 flex items-center justify-between text-white shrink-0">
          <div className="flex items-center gap-4">
            <div className="bg-white/20 backdrop-blur-md p-3 rounded-2xl">
              <span className="material-symbols-rounded text-2xl">history_toggle_off</span>
            </div>
            <div>
              <h3 className="text-base font-black tracking-widest uppercase italic leading-none mb-1">OTOMASYON TAKVİMİ</h3>
              <p className="text-[10px] font-bold opacity-80 uppercase tracking-widest">
                {camera?.camera_name || camera?.camera_id} — Akıllı Çalışma Programı
              </p>
            </div>
          </div>
          <button 
            onClick={onClose} 
            className="w-10 h-10 flex items-center justify-center hover:bg-white/20 rounded-full transition-all duration-300"
          >
            <span className="material-symbols-rounded text-2xl">close</span>
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-10 space-y-12 scrollbar-thin scrollbar-thumb-slate-200">
          
          {/* Add New Section - Card Style */}
          <div className="bg-slate-50/80 rounded-[2rem] p-8 border border-slate-100 shadow-inner">
            <div className="flex items-center gap-2 mb-6">
              <span className="material-symbols-rounded text-brand-teal text-lg">add_circle</span>
              <h4 className="text-[11px] font-black text-slate-500 uppercase tracking-widest">Planlanan Dilim Ekle</h4>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-end">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">GÜN SEÇİMİ</label>
                <select 
                  value={newEntry.day_of_week}
                  onChange={(e) => setNewEntry({...newEntry, day_of_week: parseInt(e.target.value)})}
                  className="w-full rounded-2xl border-none bg-white p-4 text-xs font-bold text-slate-700 shadow-sm focus:ring-2 ring-brand-teal/20 outline-none transition-all appearance-none cursor-pointer"
                >
                  {DAYS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </div>
              
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">AÇILIŞ (START)</label>
                <input 
                  type="time" 
                  value={newEntry.start_time}
                  onChange={(e) => setNewEntry({...newEntry, start_time: e.target.value})}
                  className="w-full rounded-2xl border-none bg-white p-4 text-xs font-bold text-slate-700 shadow-sm focus:ring-2 ring-brand-teal/20 outline-none transition-all cursor-pointer"
                />
              </div>
              
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">KAPANIŞ (END)</label>
                <input 
                  type="time" 
                  value={newEntry.end_time}
                  onChange={(e) => setNewEntry({...newEntry, end_time: e.target.value})}
                  className="w-full rounded-2xl border-none bg-white p-4 text-xs font-bold text-slate-700 shadow-sm focus:ring-2 ring-brand-teal/20 outline-none transition-all cursor-pointer"
                />
              </div>
              
              <button 
                onClick={handleAdd}
                disabled={isSaving}
                className="bg-brand-teal text-white rounded-2xl h-[52px] flex items-center justify-center text-[11px] font-black uppercase tracking-widest hover:bg-brand-teal/90 disabled:opacity-50 transition-all shadow-xl shadow-brand-teal/20 active:scale-95 group"
              >
                {isSaving ? (
                  <span className="material-symbols-rounded animate-spin">sync</span>
                ) : (
                  <div className="flex items-center gap-2">
                    PROGRAMA EKLE
                  </div>
                )}
              </button>
            </div>
          </div>

          {/* List Section */}
          <div className="space-y-6">
            <div className="flex items-center justify-between px-4">
              <h4 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em]">AKTİF PROGRAMLAR</h4>
              <span className="bg-slate-100 text-slate-500 text-[9px] font-black px-3 py-1.5 rounded-full uppercase tracking-widest">
                {schedules.length} Kayıt
              </span>
            </div>
            
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-200">
                <div className="w-12 h-12 border-4 border-slate-100 border-t-brand-teal rounded-full animate-spin"></div>
                <p className="mt-4 text-[10px] font-black uppercase tracking-widest">Veriler Çekiliyor...</p>
              </div>
            ) : schedules.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 bg-slate-50/50 rounded-[2rem] border-2 border-dashed border-slate-100 space-y-4">
                <span className="material-symbols-rounded text-slate-200 text-5xl">event_busy</span>
                <div className="text-center">
                  <p className="text-xs font-bold text-slate-400">Henüz otomatik çalışma kuralı tanımlanmamış.</p>
                  <p className="text-[10px] font-medium text-slate-300 mt-1 uppercase tracking-tighter">Yukarıdaki formu kullanarak ilk planınızı ekleyin.</p>
                </div>
              </div>
            ) : (
              <div className="grid gap-4">
                {schedules.map((s) => (
                  <div key={s.id} className="group flex items-center justify-between p-6 rounded-3xl border border-slate-100 bg-white hover:border-brand-teal/20 hover:shadow-xl transition-all duration-500">
                    <div className="flex items-center gap-6">
                      <div className="h-14 w-14 rounded-2xl bg-brand-teal/5 flex items-center justify-center text-brand-teal group-hover:bg-brand-teal group-hover:text-white transition-all duration-500">
                        <span className="material-symbols-rounded text-2xl">calendar_month</span>
                      </div>
                      <div>
                        <div className="text-sm font-black text-slate-900 tracking-tight">
                          {DAYS.find(d => d.value === s.day_of_week)?.label}
                        </div>
                        <div className="text-[10px] font-black text-brand-teal/70 uppercase tracking-widest mt-1">
                          {s.start_time.substring(0, 5)} — {s.end_time.substring(0, 5)}
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <div className="flex flex-col items-end mr-4">
                        <span className="text-[9px] font-black text-slate-300 uppercase tracking-widest">DURUM</span>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
                          <span className="text-[10px] font-black text-slate-600 uppercase">AKTİF</span>
                        </div>
                      </div>
                      <button 
                        onClick={() => handleDelete(s.id)}
                        className="w-12 h-12 flex items-center justify-center text-slate-200 hover:text-red-500 hover:bg-red-50 rounded-2xl transition-all duration-300"
                        title="Programı Kaldır"
                      >
                        <span className="material-symbols-rounded">delete_outline</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Modern Footer */}
        <div className="p-8 bg-slate-50/50 border-t border-slate-100 flex items-center justify-between shrink-0">
          <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest max-w-[300px] leading-relaxed">
            * Tanımlanan saatler sunucu saatine göredir. <br/>
            Değişiklikler bir dakika içerisinde aktif olur.
          </p>
          <button 
            onClick={onClose}
            className="px-10 py-4 rounded-2xl bg-white border border-slate-200 text-[11px] font-black text-slate-600 uppercase tracking-widest hover:bg-slate-100 hover:shadow-lg transition-all active:scale-95"
          >
            PENCEREYİ KAPAT
          </button>
        </div>
      </div>
    </div>
  );
}
