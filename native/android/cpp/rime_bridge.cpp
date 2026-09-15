#include <jni.h>
#include <rime_api.h>
#include <string>
#include <vector>
#include <stdexcept>

namespace {
RimeApi* api = nullptr;
bool initialized = false;
std::string shared_dir, user_dir;
std::string utf8(JNIEnv* env, jstring text) {
  const char* value = env->GetStringUTFChars(text, nullptr);
  std::string result(value);
  env->ReleaseStringUTFChars(text, value);
  return result;
}
jstring java_string(JNIEnv* env, const std::string& value) {
  // NewStringUTF uses modified UTF-8; byte[] constructor preserves emoji/non-BMP.
  jbyteArray bytes = env->NewByteArray(value.size());
  env->SetByteArrayRegion(bytes, 0, value.size(), reinterpret_cast<const jbyte*>(value.data()));
  jclass string_class = env->FindClass("java/lang/String");
  auto ctor = env->GetMethodID(string_class, "<init>", "([BLjava/lang/String;)V");
  jstring charset = env->NewStringUTF("UTF-8");
  auto result = static_cast<jstring>(env->NewObject(string_class, ctor, bytes, charset));
  env->DeleteLocalRef(bytes);
  env->DeleteLocalRef(charset);
  env->DeleteLocalRef(string_class);
  return result;
}
void fail(JNIEnv* env, const char* text) {
  env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), text);
}
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_conversationlens_ime_RimeEngine_open(JNIEnv* env, jclass, jstring shared, jstring user) {
  try {
    if (!initialized) {
      api = rime_get_api();
      shared_dir = utf8(env, shared);
      user_dir = utf8(env, user);
      RIME_STRUCT(RimeTraits, traits);
      traits.shared_data_dir = shared_dir.c_str();
      traits.user_data_dir = user_dir.c_str();
      traits.app_name = "rime.conversationlens";
      traits.distribution_name = "Conversation Lens";
      traits.distribution_code_name = "lens";
      traits.distribution_version = "0.12.0";
      api->setup(&traits);
      api->initialize(&traits);
      if (api->start_maintenance(True)) api->join_maintenance_thread();
      initialized = true;
    }
    auto session = api->create_session();
    if (!session || !api->select_schema(session, "lens_pinyin")) {
      if (session) api->destroy_session(session);
      throw std::runtime_error("Rime schema deployment failed");
    }
    api->set_option(session, "ascii_mode", False);
    api->set_option(session, "incognito_mode", True);
    return static_cast<jlong>(session);
  } catch (const std::exception& e) { fail(env, e.what()); return 0; }
}

extern "C" JNIEXPORT void JNICALL
Java_com_conversationlens_ime_RimeEngine_close(JNIEnv*, jclass, jlong session) {
  if (api && session) api->destroy_session(session);
}

extern "C" JNIEXPORT jobjectArray JNICALL
Java_com_conversationlens_ime_RimeEngine_step(JNIEnv* env, jclass, jlong session, jint action, jint value) {
  try {
    if (!api || !session || !api->find_session(session)) throw std::runtime_error("Rime session is unavailable");
    bool handled = true;
    switch (action) {
      case 0: handled = api->process_key(session, value, 0); break;
      case 1: handled = api->select_candidate_on_current_page(session, value); break;
      case 2: api->clear_composition(session); break;
      case 3: handled = api->change_page(session, value < 0); break;
      case 4: handled = api->commit_composition(session); break;
      case 5:
        api->clear_composition(session);
        if (!api->select_schema(session, value == 1 ? "lens_nine" : "lens_pinyin"))
          throw std::runtime_error("Rime layout deployment failed");
        api->set_option(session, "ascii_mode", False);
        api->set_option(session, "incognito_mode", True);
        break;
    }
    std::vector<std::string> result(5);
    result[0] = handled ? "1" : "0";
    RIME_STRUCT(RimeCommit, commit);
    if (api->get_commit(session, &commit)) {
      result[1] = commit.text ? commit.text : "";
      api->free_commit(&commit);
    }
    RIME_STRUCT(RimeContext, context);
    if (api->get_context(session, &context)) {
      result[2] = context.composition.preedit ? context.composition.preedit : "";
      result[3] = std::to_string(context.menu.page_no);
      result[4] = context.menu.is_last_page ? "1" : "0";
      for (int i = 0; i < context.menu.num_candidates; ++i)
        result.emplace_back(context.menu.candidates[i].text ? context.menu.candidates[i].text : "");
      api->free_context(&context);
    }
    auto array = env->NewObjectArray(result.size(), env->FindClass("java/lang/String"), nullptr);
    for (size_t i = 0; i < result.size(); ++i) {
      jstring text = java_string(env, result[i]);
      env->SetObjectArrayElement(array, i, text);
      env->DeleteLocalRef(text);
    }
    return array;
  } catch (const std::exception& e) { fail(env, e.what()); return nullptr; }
}
