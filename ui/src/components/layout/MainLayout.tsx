import { ReactNode } from 'react';
import {
    LayoutDashboard,
    Cpu,
    Activity,
    Settings,
    Briefcase,
    ScanEye,
    Satellite
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { TerminalHeader } from './TerminalHeader';

interface MainLayoutProps {
    children: ReactNode;
    activeTab: string;
    setActiveTab: (tab: string) => void;
}

export function MainLayout({ children, activeTab, setActiveTab }: MainLayoutProps) {
    return (
        <div className="min-h-screen w-full flex bg-[#050505] text-white/90 font-sans overflow-hidden">
            {/* Sidebar Navigation */}
            <nav className="w-16 lg:w-20 glass border-r border-white/5 flex flex-col items-center py-8 gap-8 z-50">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-aethelgard-cyan to-aethelgard-blue flex items-center justify-center shadow-lg shadow-aethelgard-cyan/20 group cursor-pointer transition-all hover:shadow-[0_0_20px_rgba(0,242,255,0.4)]">
                    <span className="font-outfit font-bold text-dark text-xl group-hover:scale-110 transition-transform">A</span>
                </div>

                <div className="flex flex-col gap-6 mt-12">
                    <NavIcon icon={<LayoutDashboard size={22} />} active={activeTab === 'trader'} onClick={() => setActiveTab('trader')} label="Trader" />
                    <NavIcon icon={<Activity size={22} />} active={activeTab === 'analysis'} onClick={() => setActiveTab('analysis')} label="Análisis" />
                    <NavIcon icon={<Briefcase size={22} />} active={activeTab === 'portfolio'} onClick={() => setActiveTab('portfolio')} label="Portfolio" />
                    <NavIcon icon={<Cpu size={22} />} active={activeTab === 'edge'} onClick={() => setActiveTab('edge')} label="EDGE" />
                    <NavIcon icon={<Satellite size={22} />} active={activeTab === 'satellite'} onClick={() => setActiveTab('satellite')} label="Satellite Link" />
                    <NavIcon icon={<ScanEye size={22} />} active={activeTab === 'monitor'} onClick={() => setActiveTab('monitor')} label="Monitor" />
                </div>

                <div className="mt-auto">
                    <NavIcon icon={<Settings size={22} />} active={activeTab === 'settings'} onClick={() => setActiveTab('settings')} label="Settings" />
                </div>
            </nav>

            <main className="flex-1 flex flex-col relative h-screen">
                {/* Decorative Background Elements */}
                <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-aethelgard-cyan/5 blur-[120px] rounded-full -translate-y-1/2 translate-x-1/2 pointer-events-none" />
                <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-aethelgard-blue/5 blur-[120px] rounded-full translate-y-1/2 -translate-x-1/2 pointer-events-none" />

                <TerminalHeader />

                {/* Main Content Viewport with Framer Motion Micro-interactions */}
                <div className="flex-1 p-8 overflow-y-auto scrollbar-hide relative z-10">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={activeTab}
                            initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
                            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                            exit={{ opacity: 0, scale: 0.98, filter: 'blur(4px)' }}
                            transition={{ duration: 0.3, ease: 'easeOut' }}
                            className="h-full"
                        >
                            {children}
                        </motion.div>
                    </AnimatePresence>
                </div>
            </main>
        </div>
    );
}

function NavIcon({ icon, active = false, onClick, label }: any) {
    return (
        <div className="relative group">
            <button
                onClick={onClick}
                className={`p-3 rounded-xl transition-all duration-300 ${active
                    ? 'bg-aethelgard-cyan/10 text-aethelgard-cyan border border-aethelgard-cyan/20 shadow-[0_0_15px_rgba(0,242,255,0.1)]'
                    : 'text-white/20 hover:text-white/80 hover:bg-white/5'
                    }`}
            >
                {icon}
            </button>
            <div className="absolute left-full ml-4 px-2 py-1 rounded bg-white/10 backdrop-blur-md text-[10px] text-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-[100] border border-white/5">
                {label}
            </div>
        </div>
    );
}
