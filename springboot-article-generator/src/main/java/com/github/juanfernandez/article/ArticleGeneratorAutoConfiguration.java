package com.github.juanfernandez.article;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.juanfernandez.article.article.application.ArticleGeneratorService;
import com.github.juanfernandez.article.article.application.PromptBuilderService;
import com.github.juanfernandez.article.article.application.SeoService;
import com.github.juanfernandez.article.article.application.TextUtils;
import com.github.juanfernandez.article.article.port.in.ArticleGeneratorPort;
import com.github.juanfernandez.article.shared.ai.AiClientAdapter;
import com.github.juanfernandez.article.shared.ai.port.AiPort;
import com.github.juanfernandez.article.shared.config.ArticleGeneratorProperties;
import com.github.juanfernandez.article.shared.util.JsonUtils;
import dev.langchain4j.model.chat.ChatModel;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/**
 * Spring Boot auto-configuration for the Article Generator library.
 *
 * <p>This is the <strong>primary</strong> auto-configuration. It registers all beans required
 * to generate SEO articles via {@link ArticleGeneratorPort} / {@link ArticleGeneratorService}.
 * Every bean is guarded with {@code @ConditionalOnMissingBean} so consuming applications can
 * override any individual component by declaring their own bean of the same type.
 *
 * <p>Question generation ({@code PreguntaGeneratorService}) is handled separately by
 * {@link PreguntaGeneratorAutoConfiguration}, which is only activated when a
 * {@code JpaPreguntaRepository} bean is present.
 *
 * <p>Activated automatically via
 * {@code META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports}.
 *
 * <h2>Hexagonal architecture</h2>
 * <ul>
 *   <li><strong>Shared kernel</strong>: {@link ArticleGeneratorProperties}, {@link AiPort} /
 *       {@link AiClientAdapter}, {@link JsonUtils}.</li>
 *   <li><strong>Article application layer</strong>: {@link ArticleGeneratorService} implements
 *       {@link ArticleGeneratorPort}; supported by {@link PromptBuilderService},
 *       {@link SeoService} and {@link TextUtils}.</li>
 * </ul>
 */
@AutoConfiguration
@EnableConfigurationProperties(ArticleGeneratorProperties.class)
public class ArticleGeneratorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public ObjectMapper articleGeneratorObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    @ConditionalOnMissingBean
    public JsonUtils jsonUtils(ObjectMapper objectMapper) {
        return new JsonUtils(objectMapper);
    }

    @Bean
    @ConditionalOnMissingBean
    public TextUtils textUtils() {
        return new TextUtils();
    }

    @Bean
    @ConditionalOnMissingBean
    public SeoService seoService(ArticleGeneratorProperties properties) {
        return new SeoService(properties);
    }

    @Bean
    @ConditionalOnMissingBean
    public PromptBuilderService promptBuilderService(ArticleGeneratorProperties properties) {
        return new PromptBuilderService(properties);
    }

    @Bean
    @ConditionalOnMissingBean(AiPort.class)
    public AiClientAdapter aiClientAdapter(ArticleGeneratorProperties properties,
                                           ObjectMapper objectMapper,
                                           ObjectProvider<ChatModel> chatModelProvider) {
        ChatModel chatModel = chatModelProvider.getIfAvailable();
        return new AiClientAdapter(properties, objectMapper, chatModel);
    }

    @Bean
    @ConditionalOnMissingBean(ArticleGeneratorPort.class)
    public ArticleGeneratorService articleGeneratorService(
            ArticleGeneratorProperties properties,
            AiPort aiPort,
            PromptBuilderService promptBuilderService,
            SeoService seoService,
            TextUtils textUtils,
            JsonUtils jsonUtils) {
        return new ArticleGeneratorService(
                properties, aiPort, promptBuilderService, seoService, textUtils, jsonUtils);
    }
}
