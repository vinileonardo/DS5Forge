#include <GameInput.h>
#include <windows.h>

#include <atomic>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace {
std::atomic<unsigned> g_count{0};

std::string hex_id(const APP_LOCAL_DEVICE_ID& id) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(&id);
    std::ostringstream out;
    for (size_t i = 0; i < sizeof(id); ++i) {
        out << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(bytes[i]);
    }
    return out.str();
}

void CALLBACK on_device(
    GameInputCallbackToken,
    void*,
    IGameInputDevice* device,
    uint64_t,
    GameInputDeviceStatus current_status,
    GameInputDeviceStatus) {
    if ((current_status & GameInputDeviceConnected) == 0 || device == nullptr) {
        return;
    }
    const GameInputDeviceInfo* info = device->GetDeviceInfo();
    if (info == nullptr) {
        return;
    }
    const unsigned index = g_count.fetch_add(1);
    std::string name;
    if (info->displayName != nullptr && info->displayName->data != nullptr) {
        name.assign(info->displayName->data, info->displayName->sizeInBytes);
        while (!name.empty() && name.back() == '\0') {
            name.pop_back();
        }
    }
    std::cout
        << "DEVICE[" << index << "]"
        << " vid=0x" << std::hex << std::setw(4) << std::setfill('0') << info->vendorId
        << " pid=0x" << std::setw(4) << info->productId
        << std::dec
        << " interface=" << static_cast<unsigned>(info->interfaceNumber)
        << " collection=" << static_cast<unsigned>(info->collectionNumber)
        << " supportedInput=0x" << std::hex << static_cast<uint32_t>(info->supportedInput) << std::dec
        << " axes=" << info->controllerAxisCount
        << " buttons=" << info->controllerButtonCount
        << " switches=" << info->controllerSwitchCount
        << " deviceId=" << hex_id(info->deviceId)
        << " rootId=" << hex_id(info->deviceRootId)
        << " name=\"" << name << "\""
        << std::endl;
}
}  // namespace

int wmain() {
    IGameInput* game_input = nullptr;
    const HRESULT created = GameInputCreate(&game_input);
    if (FAILED(created) || game_input == nullptr) {
        std::cerr << "GameInputCreate failed: 0x" << std::hex << static_cast<unsigned long>(created) << std::endl;
        return 2;
    }

    GameInputCallbackToken token{};
    const HRESULT registered = game_input->RegisterDeviceCallback(
        nullptr,
        static_cast<GameInputKind>(GameInputKindGamepad | GameInputKindController),
        GameInputDeviceAnyStatus,
        GameInputBlockingEnumeration,
        nullptr,
        on_device,
        &token);
    if (FAILED(registered)) {
        std::cerr << "RegisterDeviceCallback failed: 0x" << std::hex << static_cast<unsigned long>(registered) << std::endl;
        game_input->Release();
        return 3;
    }

    game_input->UnregisterCallback(token, 5000);
    std::cout << "COUNT=" << g_count.load() << std::endl;
    game_input->Release();
    return 0;
}
