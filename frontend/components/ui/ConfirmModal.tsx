"use client";

import React from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  type?: "danger" | "warning" | "info";
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title,
  message,
  confirmText = "Onayla",
  cancelText = "İptal",
  onConfirm,
  onCancel,
  type = "danger",
}) => {
  if (!isOpen) return null;

  const themes = {
    danger: {
      icon: <AlertTriangle className="w-6 h-6 text-red-500" />,
      button: "bg-red-500 hover:bg-red-600 shadow-red-500/20",
      bg: "bg-red-50",
    },
    warning: {
      icon: <AlertTriangle className="w-6 h-6 text-amber-500" />,
      button: "bg-amber-500 hover:bg-amber-600 shadow-amber-500/20",
      bg: "bg-amber-50",
    },
    info: {
      icon: <AlertTriangle className="w-6 h-6 text-brand-teal" />,
      button: "bg-brand-teal hover:bg-brand-teal/90 shadow-brand-teal/20",
      bg: "bg-teal-50",
    },
  };

  const theme = themes[type];

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
        onClick={onCancel}
      />
      
      {/* Modal Content */}
      <div className="relative w-full max-w-md bg-white rounded-[2rem] shadow-2xl overflow-hidden animate-scale-up border border-slate-100">
        <div className="p-8">
          <div className="flex items-start justify-between mb-6">
            <div className={`p-3 rounded-2xl ${theme.bg}`}>
              {theme.icon}
            </div>
            <button 
              onClick={onCancel}
              className="p-2 hover:bg-slate-50 rounded-xl transition-colors text-slate-400 hover:text-slate-600"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <h3 className="text-xl font-black text-slate-900 mb-2 uppercase tracking-tight">
            {title}
          </h3>
          <p className="text-slate-500 text-sm leading-relaxed mb-8">
            {message}
          </p>

          <div className="flex gap-3">
            <button
              onClick={onCancel}
              className="flex-1 px-6 py-3.5 rounded-xl border border-slate-200 text-slate-600 text-xs font-black uppercase tracking-widest hover:bg-slate-50 transition-all active:scale-95"
            >
              {cancelText}
            </button>
            <button
              onClick={onConfirm}
              className={`flex-1 px-6 py-3.5 rounded-xl text-white text-xs font-black uppercase tracking-widest transition-all shadow-lg active:scale-95 ${theme.button}`}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
