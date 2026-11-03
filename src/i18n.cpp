#include "i18n.hpp"
#include <array>
#include <atomic>
#include <map>
#include <mutex>
#include <nlohmann/json.hpp>
#include "translations_data.h"
namespace lab {
static constexpr const char* codes[]={"it","en","de","es","fr","pt","nl","pl","ro","sv","zh-CN","zh-TW","ja","ko","hi","ru","ar","bn","id","tr","vi","ur"};
static constexpr const char* names[]={"Italiano","English","Deutsch","Español","Français","Português","Nederlands","Polski","Română","Svenska","简体中文","繁體中文","日本語","한국어","हिन्दी","Русский","العربية","বাংলা","Bahasa Indonesia","Türkçe","Tiếng Việt","اردو"};
static std::atomic<int> language{0};
int languageCount(){return 22;}
const char* languageCode(int i){return codes[i>=0&&i<22?i:0];}
const char* languageName(int i){return names[i>=0&&i<22?i:0];}
int languageIndex(const std::string& code){for(int i=0;i<22;i++)if(code==codes[i])return i;return 0;}
void setLanguage(int i){language=i>=0&&i<22?i:0;}
int currentLanguage(){return language;}
static const auto& translations(){
 static const auto catalog=nlohmann::json::parse(translationsData).get<std::map<std::string,std::array<std::string,21>>>();return catalog;
}
const char* translate(const char* key){
    int selected=language.load();if(!key||!*key||selected==0)return key?key:"";
    const auto& catalog=translations();
    auto found=catalog.find(key);if(found!=catalog.end())return found->second.at(selected-1).c_str();
    // Notices retain their canonical template after formatting. Cache immutable
    // strings so several translated values can safely share one draw call.
    static std::mutex mutex;static std::map<std::pair<int,std::string>,std::string> notices;
    std::lock_guard lock(mutex);auto cacheKey=std::make_pair(selected,std::string(key));
    if(auto cached=notices.find(cacheKey);cached!=notices.end())return cached->second.c_str();
    std::string raw=key;
    for(const auto& [source,values]:catalog){
        auto at=source.find('%');if(at==std::string::npos||at+1>=source.size()||(source[at+1]!='s'&&source[at+1]!='d')||source.find('%',at+1)!=std::string::npos)continue;
        auto prefix=source.substr(0,at),suffix=source.substr(at+2);
        if(raw.size()<prefix.size()+suffix.size()||!raw.starts_with(prefix)||!raw.ends_with(suffix))continue;
        auto argument=raw.substr(prefix.size(),raw.size()-prefix.size()-suffix.size());
        if(source[at+1]=='d'&&(argument.empty()||argument.find_first_not_of("0123456789")!=std::string::npos))continue;
        auto text=values[selected-1];text.replace(text.find(source.substr(at,2)),2,argument);
        return notices.emplace(cacheKey,std::move(text)).first->second.c_str();
    }
    return key;
}
// Diagnostics are localized at display time, not when a worker stores its result.
// Raw vendor text belongs in the diagnostic log, never in the translated UI body.
std::string diagnosticText(const std::string& raw){
 if(raw.empty())return {};
 if(translations().contains(raw))return translate(raw.c_str());
 static const auto rules=nlohmann::json::parse(uiMessagesData).get<std::map<std::string,std::string>>();
 const std::string* key=nullptr;size_t length=0;
 for(const auto& [prefix,message]:rules)if(prefix.size()>length&&raw.starts_with(prefix)){key=&message;length=prefix.size();}
 return translate(key?key->c_str():"Operazione non riuscita. Dettagli nel registro.");
}
}
extern "C" const char* lab_tr(const char* key){return lab::translate(key);}
