// P0-43: service-owned camera inventory boundary.
// This is an in-process LocalSystem-only worker probe. It does not
// capture, identify, attest video frames or perform liveness detection.
// Future secure capture must be implemented separately.
#pragma once
#include "service_identity.h"
#include "camera_capability.h"
namespace safepckids_protected_camera {
enum class State { NotSystem, NoDevice, AvailableUnverified, BackendFailed };
struct Observation {
    State state=State::BackendFailed;
    safepckids_camera::DeviceInventory inventory={};
    // No camera count, client-supplied flags or "worker identity"
    // ever becomes Windows authentication evidence.
    bool trusted_face() const {return false;}
    bool trusted_liveness() const {return false;}
};
inline Observation inspect_local_system() {
    if(safepckids_service_identity::current_process_identity() !=
       safepckids_service_identity::ServiceIdentity::LocalSystem)
       return {State::NotSystem,{}};
    const auto device=safepckids_camera::enumerate();
    State state=State::BackendFailed;
    switch(device.capability) {
      case safepckids_camera::Capability::NoCamera: state=State::NoDevice; break;
      case safepckids_camera::Capability::EnumeratedOnly:
        state=State::AvailableUnverified; break;
      default: state=State::BackendFailed; break;
    }
    return {state,device};
}
inline bool self_test() {
    // Pure assertions: even camera detection cannot assert live identity.
    Observation pretend={State::AvailableUnverified,{}};
    pretend.inventory.device_count=7;
    if(pretend.trusted_face()||pretend.trusted_liveness())return false;
    Observation no_device={State::NoDevice,{}};
    if(no_device.trusted_face()||no_device.trusted_liveness())return false;
    // Non-SYSTEM diagnostic hosts must never enumerate as a trusted worker.
    if(safepckids_service_identity::current_process_identity() ==
       safepckids_service_identity::ServiceIdentity::NotLocalSystem) {
       auto result=inspect_local_system();
       if(result.state!=State::NotSystem ||
          result.trusted_face() || result.trusted_liveness()) return false;
    }
    return true;
}
} // namespace safepckids_protected_camera
