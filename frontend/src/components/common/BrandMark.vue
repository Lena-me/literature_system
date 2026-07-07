<template>
  <div class="brand-mark">
    <svg class="brand-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </svg>
    <div class="brand-text">
      <strong>睿识</strong>
      <span>Nous Knowledge OS</span>
    </div>
  </div>
</template>

<style scoped>
.brand-mark {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  color: var(--academic-primary);
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

strong {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--academic-text-main);
  line-height: 1;
}

span {
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.5px;
  color: var(--academic-text-muted);
  line-height: 1.2;
}
</style>
