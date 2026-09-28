"use client";

import React from "react";
import Image from "next/image";
import {
  X,
  LayoutDashboard,
  UploadCloud,
  Activity,
  Radar,
  Users,
  ShieldCheck,
  ListChecks,
  LucideIcon,
} from "lucide-react";

interface SidebarProps {
  path: string;
  setPath: (path: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

interface NavItemDef {
  href: string;
  label: string;
  icon: LucideIcon;
}

export function Sidebar({ path, setPath, isOpen, onClose }: SidebarProps) {
  const navItem = ({ href, label, icon: Icon }: NavItemDef) => {
    const isActive = path === href;
    return (
      <button
        key={href}
        type="button"
        onClick={() => {
          setPath(href);
          onClose();
        }}
        className={`w-full flex items-center gap-3 px-3 py-2 my-0.5 text-sm rounded-lg transition-colors text-left cursor-pointer focus:outline-none ${
          isActive
            ? "bg-blue-600 text-white font-medium"
            : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 font-normal"
        }`}
      >
        <Icon
          className={`w-4 h-4 flex-shrink-0 ${
            isActive ? "text-white" : "text-slate-400 group-hover:text-slate-200"
          }`}
        />
        <span className="flex-1 truncate">{label}</span>
      </button>
    );
  };

  return (
    <>
      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="bg-black/50 fixed inset-0 z-40 transition-opacity duration-200"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Clean Professional Sidebar Drawer */}
      <aside
        className={`fixed top-0 left-0 h-screen w-64 z-50 transform transition-transform duration-200 ease-in-out flex flex-col bg-slate-900 border-r border-slate-800 shadow-xl overflow-y-auto ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Supervisory navigation drawer"
      >
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            {/* Clean white badge for logo visibility */}
            <div className="w-9 h-9 rounded-lg bg-white p-1 flex items-center justify-center flex-shrink-0 shadow-sm border border-slate-200/10">
              <Image
                src="/SAT-SA.png"
                alt="SAT-SA Logo"
                width={30}
                height={30}
                className="w-full h-full object-contain"
                priority
              />
            </div>
            <div className="flex flex-col">
              <span className="text-white font-bold text-base tracking-tight leading-tight">
                SAT-SA
              </span>
              <span className="text-[11px] text-slate-400 font-normal leading-tight">
                SOC Assessment
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-slate-700 cursor-pointer"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="p-3 flex-1 space-y-4" aria-label="Primary navigation">
          {/* Section: Analytics */}
          <div>
            <div className="px-3 pb-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Analytics
            </div>
            <div className="space-y-0.5">
              {navItem({ href: "/", label: "Dashboard Overview", icon: LayoutDashboard })}
              {navItem({ href: "/data-ingestion", label: "Data Ingestion", icon: UploadCloud })}
            </div>
          </div>

          <div className="h-px bg-slate-800 mx-2" />

          {/* Section: Supervisory Views */}
          <div>
            <div className="px-3 pb-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Supervisory Views
            </div>
            <div className="space-y-0.5">
              {navItem({ href: "/execution-gaps", label: "Execution Gaps", icon: Activity })}
              {navItem({ href: "/negative-space", label: "Negative Space", icon: Radar })}
              {navItem({ href: "/peer-comparison", label: "Peer Comparison", icon: Users })}
              {navItem({ href: "/prioritizer", label: "AI Prioritization & CAPA", icon: ListChecks })}
            </div>
          </div>

          <div className="h-px bg-slate-800 mx-2" />

          {/* Section: Records */}
          <div>
            <div className="px-3 pb-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Records
            </div>
            <div className="space-y-0.5">
              {navItem({ href: "/audit-reports", label: "Audit Reports", icon: ShieldCheck })}
            </div>
          </div>
        </nav>
      </aside>
    </>
  );
}

export default Sidebar;
