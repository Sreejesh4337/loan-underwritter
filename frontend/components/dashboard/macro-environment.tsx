export function MacroEnvironment() {
  return (
    <div className="bg-ds-primary-container rounded-lg p-4 text-white relative overflow-hidden">
      <div className="relative z-10">
        <p className="text-[10px] font-mono font-medium text-ds-primary-fixed-dim uppercase tracking-wider mb-2 leading-[14px]">
          Macro Environment
        </p>
        <div className="flex justify-between items-end">
          <div>
            <p className="text-[10px] font-mono font-medium text-outline-variant leading-[14px]">
              SOFR
            </p>
            <p className="text-2xl font-semibold leading-8 tracking-[-0.01em]">
              5.32%
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-mono font-medium text-ds-secondary-fixed leading-[14px]">
              Target Spread
            </p>
            <p className="text-sm leading-5">+ 250 bps</p>
          </div>
        </div>
      </div>

      {/* Abstract Background element */}
      <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-[#3f465c] rounded-full opacity-20 blur-2xl" />
    </div>
  );
}
