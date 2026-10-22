// Temporary validation firmware: no SD/save writes. Restore your game afterward.
#include <CHGame.h>

extern "C" {
__attribute__((used, aligned(16))) volatile uint32_t register_probe[40];
void probe_regs_t2(void);
void probe_regs_t3(void);
uint32_t probe_xw(void);
}

volatile uint32_t software_irqs, nested_ok, nested_fail;
volatile bool test_nesting;
uint32_t xw_errors, register_errors, passes;

extern "C" __attribute__((noinline, noclone)) void irq_work(void) {
    ++software_irqs;
    register_probe[0] = 1;
}

extern "C" void SW_Handler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
extern "C" void SW_Handler(void) {
    NVIC_ClearPendingIRQ(Software_IRQn);
    // Write every hardware-saved and ABI-preserved integer register, then call
    // a separate function. The compiler must preserve the s-registers itself.
    __asm__ volatile (
        "li ra,769\n li t0,773\n li t1,774\n li t2,775\n"
        "li s0,776\n li s1,777\n"
        "li a0,778\n li a1,779\n li a2,780\n li a3,781\n"
        "li a4,782\n li a5,783\n li a6,784\n li a7,785\n"
        "li s2,786\n li s3,787\n li s4,788\n li s5,789\n"
        "li s6,790\n li s7,791\n li s8,792\n li s9,793\n"
        "li s10,794\n li s11,795\n"
        "li t3,796\n li t4,797\n li t5,798\n li t6,799\n"
        ::: "ra", "t0", "t1", "t2", "t3", "t4", "t5", "t6",
            "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
            "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
            "s8", "s9", "s10", "s11", "memory");
    irq_work();
}

extern "C" void osSystickHandler(void) {
    if (!test_nesting) return;
    register_probe[0] = 0;
    NVIC_SetPendingIRQ(Software_IRQn);
    // A higher-priority software IRQ should finish while this tick is active.
    for (unsigned i = 0; i < 2000 && !register_probe[0]; ++i)
        __asm__ volatile ("nop");
    if (register_probe[0]) ++nested_ok;
    else ++nested_fail;
}

static uint32_t checkRegisters(unsigned scratch) {
    uint32_t errors = register_probe[1] != register_probe[2];
    for (unsigned reg = 1; reg < 32; ++reg) {
        if (reg == 2 || reg == scratch) continue;
        uint32_t expected = 0x100 + reg;
        if (reg == 3) expected = register_probe[35];
        else if (reg == 4) expected = register_probe[36];
        else if (reg == 5) expected = 0xe000e000;
        else if (reg == 6) expected = 0x4000;
        else if (reg == 27) expected = (uint32_t)(uintptr_t)register_probe;
        if (register_probe[3 + reg] != expected) ++errors;
    }
    return errors;
}

static void runChecks() {
    xw_errors = probe_xw();
    register_errors = 0;
    software_irqs = nested_ok = nested_fail = 0;
    for (unsigned i = 0; i < 10000; ++i) {
        probe_regs_t2();
        register_errors += checkRegisters(7);
        probe_regs_t3();
        register_errors += checkRegisters(28);
    }
    test_nesting = true;
    delay(100);
    test_nesting = false;
    ++passes;
}

static void report() {
    Serial.print("PORTPROBE gcc=" __VERSION__ " xw_cases=64 xw_errors=");
    Serial.print(xw_errors);
    Serial.print(" register_trials=20000 register_errors=");
    Serial.print(register_errors);
    Serial.print(" software_irqs="); Serial.print(software_irqs);
    Serial.print(" nested_ok="); Serial.print(nested_ok);
    Serial.print(" nested_fail="); Serial.print(nested_fail);
    Serial.print(" passes="); Serial.println(passes);
}

void setup() {
    chgame.boot();
    chgame.startExits = false;
    gfx_begin(GFX_DIV2, GFX_12BPP);
    pal::init();
    Serial.begin();
    NVIC_SetPriority(Software_IRQn, 0);
    NVIC_EnableIRQ(Software_IRQn);
    runChecks();
    gfx_clear(0);
    text35x2s(8, 12, "GCC PORT", 1);
    text35(8, 40, xw_errors || register_errors || nested_fail || !nested_ok ? "CHECK FAILED" : "PROBES PASS", 1);
    gfx_flushAsync();
}

void loop() {
    while (Serial.available()) {
        int command = Serial.read();
        if (command == 'R') runChecks();
        if (command == '?' || command == 'R') report();
    }
}
